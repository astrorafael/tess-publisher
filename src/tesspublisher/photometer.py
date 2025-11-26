# ----------------------------------------------------------------------
# Copyright (c) 2025 Rafael Gonzalez.
#
# See the LICENSE file for details
# ----------------------------------------------------------------------

import json
import logging
import asyncio
import collections
from asyncio import PriorityQueue
from datetime import datetime, timezone, timedelta
from typing import Any

import aioserial
import serial

from .logger import LogSpace
from .constants import MessagePriority
from .model import PhotometerInfo

# ----------------
# Global variables
# ----------------


class Photometer:
    def __init__(self, port: str, period: int, info: PhotometerInfo, mqtt_queue: PriorityQueue):
        self.log = logging.getLogger(info.name)
        self.info = info
        self.mqtt_queue = mqtt_queue
        self.queue = collections.deque(maxlen=1)  # ring buffer 1 slot long
        self.port = port
        self.period = period
        self.serial = None
        self.counter = 0

    async def register(self) -> None:
        message = self.info.to_dict()
        await self.mqtt_queue.put((MessagePriority.MQTT_REGISTER, message))
        await asyncio.sleep(5)
        await self.mqtt_queue.put((MessagePriority.MQTT_REGISTER, message))

    def open(self) -> None:
        try:
            self.serial = aioserial.AioSerial(port=self.port, baudrate=9600)
        except serial.serialutil.SerialException as e:
            self.log.error(e)
            raise
        else:
            self.log.info("using port %s", self.port)

    async def read(self) -> dict[str, Any] | None:
        message = (await self.serial.readline_async()).decode("utf-8")
        now = datetime.now(timezone.utc)
        try:
            message = json.loads(message)
        except json.decoder.JSONDecodeError:
            return None
        else:
            if isinstance(message, dict):
                message["tstamp"] = (now + timedelta(seconds=0.5)).strftime("%Y-%m-%dT%H:%M:%S")
                return message

    async def reader(self) -> None:
        """Photometer reader task"""
        await self.register()
        while True:
            try:
                message = await self.read()
                if message:
                    self.queue.append(message)
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
            except Exception as e:
                self.log.exception(e)
                break
