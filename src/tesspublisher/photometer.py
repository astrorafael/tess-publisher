# ----------------------------------------------------------------------
# Copyright (c) 2025 Rafael Gonzalez.
#
# See the LICENSE file for details
# ----------------------------------------------------------------------

import json
from logging import Logger
import asyncio
import collections
from asyncio import PriorityQueue
from datetime import datetime, timezone, timedelta
from typing import AsyncIterator, Optional, Any, Union


from .constants import MessagePriority
from .model import PhotometerInfo
from .transport import SerialTransport, TCPProtocol

# ----------------
# Global variables
# ----------------


class PhotometerReadings:
    def __init__(
        self,
        comm: Union[SerialTransport, TCPProtocol],
    ):
        self.comm = comm

    def __aiter__(self) -> AsyncIterator[str]:
        """
        Método para inicializar el iterador asíncrono.
        Retorna un AsyncIterator de enteros (puedes cambiar el tipo).
        """
        return aiter(self.comm)

    async def __anext__(self) -> str:
        """
        Método para obtener el siguiente ítem asincrónico.
        Retorna un entero o lanza StopAsyncIteration para finalizar la iteración.
        """
        return await anext(self.comm)


class Photometer:
    def __init__(
        self,
        comm: Union[SerialTransport, TCPProtocol],
        period: int,
        info: PhotometerInfo,
        mqtt_queue: PriorityQueue,
        logger: Logger,
    ):
        self.comm = comm
        self.log = logger
        self.info = info
        self.mqtt_queue = mqtt_queue
        self.queue = collections.deque(maxlen=1)  # ring buffer 1 slot long
        self.period = period
        self.counter = 0
        self.readings = PhotometerReadings(comm)

    async def register(self) -> None:
        message = self.info.to_dict()
        self.log.info(message)
        tstamp = datetime.now(timezone.utc)
        await self.mqtt_queue.put((MessagePriority.MQTT_REGISTER, tstamp, message))
        self.log.info("Waiting before sending register message again")
        await asyncio.sleep(5)
        tstamp = datetime.now(timezone.utc)
        await self.mqtt_queue.put((MessagePriority.MQTT_REGISTER, tstamp, message))

    async def __aenter__(self) -> "Photometer":
        """
        Método para entrar en el contexto async.
        Retorna una instancia de la clase.
        """
        # Lógica para entrar en el contexto asíncrono
        await self.comm.open()
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
        if exc_type is not None:
            await self.comm.close()
        return False

    async def reader(self) -> None:
        """Photometer reader task"""
        await self.register()
        async with self:  # Open the device
            async for message in self.readings:
                if message:
                    try:
                        message = json.loads(message)
                    except json.decoder.JSONDecodeError:
                        pass
                    else:
                        if isinstance(message, dict):
                            tstamp = datetime.now(timezone.utc) + timedelta(seconds=0.5)
                            message["tstamp"] = tstamp.strftime("%Y-%m-%dT%H:%M:%SZ")
                            self.queue.append(message)  # Internal deque

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
                    tstamp = datetime.now(timezone.utc)
                    await self.mqtt_queue.put((MessagePriority.MQTT_READINGS, tstamp, message))
                else:
                    self.log.warn("missing data. Check serial port")
            except Exception as e:
                self.log.exception(e)
                break
