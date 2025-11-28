# ----------------------------------------------------------------------
# Copyright (c) 2025 Rafael Gonzalez.
#
# See the LICENSE file for details
# ----------------------------------------------------------------------

import json
import logging
from logging import Logger
import asyncio
import collections
from asyncio import PriorityQueue
from datetime import datetime, timezone, timedelta
from typing import AsyncIterator, Optional, Any

import aioserial
import serial

from . import logger
from .constants import MessagePriority, Model as PhotometerModel
from .model import PhotometerInfo


# ----------------
# Global variables
# ----------------


class Photometer:
    def __init__(
        self,
        endpoint: str,
        period: int,
        info: PhotometerInfo,
        mqtt_queue: PriorityQueue,
        log_level: str = "info",
    ):
        self.log = logging.getLogger(info.name)
        self.log_level = logger.level(log_level)
        self.log.setLevel(self.log_level)
        self.info = info
        self.mqtt_queue = mqtt_queue
        self.queue = collections.deque(maxlen=1)  # ring buffer 1 slot long
        self.period = period
        self.counter = 0
        self.endpoint = endpoint
        self.transport = TransportBuilder(name=info.name, endpoint=endpoint, log_level=log_level)

    async def register(self) -> None:
        message = self.info.to_dict()
        await self.mqtt_queue.put((MessagePriority.MQTT_REGISTER, message))
        await asyncio.sleep(5)
        await self.mqtt_queue.put((MessagePriority.MQTT_REGISTER, message))

    async def open(self) -> None:
        try:
            await self.transport.open()
        except Exception as e:
            self.log.error(e)
            raise
        else:
            self.log.info("using endpoint %s", self.endpoint)

    async def read(self) -> dict[str, Any] | None:
        message, tstamp = await self.transport.read()
        result = None
        try:
            message = json.loads(message)
        except json.decoder.JSONDecodeError:
            pass
        else:
            if isinstance(message, dict):
                message["tstamp"] = (tstamp + timedelta(seconds=0.5)).strftime("%Y-%m-%dT%H:%M:%SZ")
                result = message
        return result

    async def reader(self) -> None:
        """Photometer reader task"""
        await self.register()
        while True:
            try:
                message = await self.read()
                if message:
                    self.queue.append(message)
            except serial.serialutil.SerialException as e:
                self.log.error(e)
                break
            except Exception as e:
                self.log.exception(e)
                break

    async def sampler(self) -> None:
        """Photometer sampler task"""
        while True:
            try:
                await asyncio.sleep(self.period)
                if len(self.queue):
                    message = self.queue.pop()
                    message["seq"] = self.counter
                    self.counter += 1
                    self.log.info(message)
                    await self.mqtt_queue.put((MessagePriority.MQTT_READINGS, message))
                else:
                    self.log.warn("missing data. Check serial port")
            except Exception as e:
                self.log.exception(e)
                break


class PhotometerReadings:
    def __init__(
        self,
        transport: Any,
    ):
        self.transport = transport

    def __aiter__(self) -> AsyncIterator[int]:
        """
        Método para inicializar el iterador asíncrono.
        Retorna un AsyncIterator de enteros (puedes cambiar el tipo).
        """
        return self

    async def __anext__(self) -> int:
        """
        Método para obtener el siguiente ítem asincrónico.
        Retorna un entero o lanza StopAsyncIteration para finalizar la iteración.
        """
        # Lógica para obtener el siguiente elemento
        # Ejemplo simplificado, levantar StopAsyncIteration para terminar
        raise StopAsyncIteration


class Photometer:
    def __init__(
        self,
        transport: Any,
        period: int,
        info: PhotometerInfo,
        mqtt_queue: PriorityQueue,
        logger: Logger,
    ):
        self.transport = transport
        self.log = logger
        self.info = info
        self.mqtt_queue = mqtt_queue
        self.queue = collections.deque(maxlen=1)  # ring buffer 1 slot long
        self.period = period
        self.counter = 0
        self.readings = PhotometerReadings(transport)

    async def register(self) -> None:
        message = self.info.to_dict()
        await self.mqtt_queue.put((MessagePriority.MQTT_REGISTER, message))
        await asyncio.sleep(5)
        await self.mqtt_queue.put((MessagePriority.MQTT_REGISTER, message))

    async def __aenter__(self) -> "Photometer":
        """
        Método para entrar en el contexto async.
        Retorna una instancia de la clase.
        """
        # Lógica para entrar en el contexto asíncrono
        await self.transport.open()
        return self

    async def __aexit__(
        self, exc_type: Optional[type], exc_val: Optional[BaseException], exc_tb: Optional[Any]
    ) -> Optional[bool]:
        """
        Método para salir del contexto async.
        Parámetros de excepción opcionales.
        Retorna opcionalmente un booleano para suprimir excepciones.
        """
        # Lógica para salir del contexto asíncrono
        return None

    async def reader(self) -> None:
        """Photometer reader task"""
        await self.register()
        async with self:
            async for message in self.readings:
                if message:
                    self.log.info(message)
                    self.queue.append(message)

    async def sampler(self) -> None:
        """Photometer sampler task"""
        while True:
            try:
                await asyncio.sleep(self.period)
                if len(self.queue):
                    message = self.queue.pop()
                    message["seq"] = self.counter
                    self.counter += 1
                    self.log.info(message)
                    await self.mqtt_queue.put((MessagePriority.MQTT_READINGS, message))
                else:
                    self.log.warn("missing data. Check serial port")
            except Exception as e:
                self.log.exception(e)
                break
