import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Tuple

import aioserial
import serial

from . import logger


def chop(endpoint: str, sep=":"):
    """Chop a list of strings, separated by sep and
    strips individual string items from leading and trailing blanks"""
    chopped = tuple(elem.strip() for elem in endpoint.split(sep))
    if len(chopped) == 1 and chopped[0] == "":
        chopped = tuple()
    return chopped


class TCPTransportOld(asyncio.Protocol):
    def __init__(self, parent, host="192.168.4.1", port=23):
        self.parent = parent
        self.log = parent.log
        self.host = host
        self.port = port
        self.log.info("Using %s Transport", self.__class__.__name__)

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        now = datetime.now(timezone.utc)
        self.parent.handle_readings(data, now)

    def connection_lost(self, exc):
        if not self.on_conn_lost.cancelled():
            self.on_conn_lost.set_result(True)

    async def readings(self):
        loop = asyncio.get_running_loop()
        self.on_conn_lost = loop.create_future()
        transport, self.protocol = await loop.create_connection(lambda: self, self.host, self.port)
        try:
            await self.on_conn_lost
        finally:
            self.transport.close()


class TCPTransport(asyncio.Protocol):
    def __init__(self, name: str, host: str="192.168.4.1", port: int=23, log_level: str="info"):
        self.log = logging.getLogger(name)
        self.log_level = logger.level(log_level)
        self.host = host
        self.port = port
        self.log.info("Using %s Transport", self.__class__.__name__)

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        now = datetime.now(timezone.utc)
        data = data.decode("utf-8")
        if not self.on_data_received.cancelled() and not self.on_data_received.done():
            self.on_data_received.set_result((data, now))

    def connection_lost(self, exc):
        if not self.on_conn_lost.cancelled():
            self.on_conn_lost.set_result(True)

    async def open(self) -> None:
        loop = asyncio.get_running_loop()
        transport, self.protocol = await loop.create_connection(lambda: self, self.host, self.port)

    async def read(self) -> Tuple[str, datetime]:
        self.on_data_received = asyncio.get_running_loop().create_future()
        data, now = await self.on_data_received
        self.log.debug(data)
        return data, now
    
    async def close(self):
        try:
            await self.on_conn_lost
        finally:
            self.transport.close()


class SerialTransport:
    def __init__(self, name: str, port="/dev/ttyUSB0", baudrate=9600, log_level: str ="info"):
        self.log = logging.getLogger(name)
        self.log_level = logger.level(log_level)
        self.port = port
        self.baudrate = baudrate
        self.serial = None
        self.log.info("Using %s Transport", self.__class__.__name__)

    async def open(self) -> None:
        try:
            self.serial = aioserial.AioSerial(port=self.port, baudrate=self.baudrate)
        except serial.serialutil.SerialException as e:
            self.log.error(e)
            raise
        else:
            self.log.info("using port %s", self.port)

    async def read(self) -> Tuple[str, datetime]:
        data = (await self.serial.readline_async()).decode("utf-8")
        now = datetime.now(timezone.utc)
        self.log.debug(data)
        return data, now



class TransportBuilder:
    def __init__(self, name: str, endpoint: str, log_level: str ="info"):
        self.name = name
        self.endpoint = endpoint
        self.log_level = log_level 
    

    def build(self):
        proto, A, B = chop(self.endpoint)
        if proto == "serial":
            return SerialTransport(name=self.name, port=A, baudrate=B, log_level=self.log_level)
        elif  proto == "tcp":
            return TCPTransport(name=self.name, host=A, port=B, log_level=self.log_level)
        else:
            raise NotImplementedError(f"Unsupported protocol: {proto}")


