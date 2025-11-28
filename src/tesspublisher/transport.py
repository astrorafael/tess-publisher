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

class TCPTransport(asyncio.Protocol):
    def __init__(
        self,
        name: str,
        host: str = "192.168.4.1",
        port: int = 23,
        log_level: str = "info",
        loop: asyncio.AbstractEventLoop | None = None,
        encoding: str = "utf-8",
        newline: bytes = b"\n",
    ) -> None:
        self.loop = loop or asyncio.get_event_loop()
        self.log = logging.getLogger(name)

        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
        self.log.setLevel(self.log_level)

        self.host = host
        self.port = port

        self.encoding = encoding
        self.newline = newline

        # Futures for external awaiters
        self.on_data_received: asyncio.Future | None = None
        self.on_conn_lost: asyncio.Future = self.loop.create_future()

        # Internal state
        self.transport: asyncio.Transport | None = None
        self._buffer = bytearray()

        self.log.info("Using %s Transport", self.__class__.__name__)

    def next_message(self) -> asyncio.Future:
        """Return a future that will be completed with (line_str, timestamp)."""
        if self.on_data_received is not None and not self.on_data_received.done():
            self.on_data_received.cancel()
        self.on_data_received = self.loop.create_future()
        return self.on_data_received

    # asyncio.Protocol callbacks

    def connection_made(self, transport: asyncio.Transport) -> None:
        self.transport = transport

    def data_received(self, data: bytes) -> None:
        # Accumulate incoming bytes
        self._buffer.extend(data)

        # Process all complete lines currently in buffer
        while True:
            idx = self._buffer.find(self.newline)
            if idx == -1:
                break  # no full line yet

            # Extract one line including newline
            line = self._buffer[: idx + len(self.newline)]
            del self._buffer[: idx + len(self.newline)]

            now = datetime.now(timezone.utc)
            text = line.decode(self.encoding, errors="replace")

            if (
                self.on_data_received is not None
                and not self.on_data_received.cancelled()
                and not self.on_data_received.done()
            ):
                self.on_data_received.set_result((text, now))
                # Only fulfill one waiter; caller can call next_message() again.
                break

    def connection_lost(self, exc: Exception | None) -> None:
        if not self.on_conn_lost.cancelled() and not self.on_conn_lost.done():
            self.on_conn_lost.set_result(True)

        if (
            self.on_data_received is not None
            and not self.on_data_received.done()
            and not self.on_data_received.cancelled()
        ):
            self.on_data_received.set_exception(
                ConnectionError("Connection lost before line was complete")
            )

class TCPTransportLineIterator:
    """Async iterator for newline-terminated messages from TCPTransport."""

    def __init__(self, protocol: TCPTransport) -> None:
        self._protocol = protocol

    def __aiter__(self):
        return self

    async def __anext__(self):
        # Await next message future from protocol
        try:
            line, timestamp = await self._protocol.next_message()
            return line, timestamp
        except ConnectionError:
            # When connection lost and no more messages, stop iteration
            raise StopAsyncIteration


async def main():
    loop = asyncio.get_running_loop()

    def factory():
        return TCPTransport("tcp-client", loop=loop)

    transport, protocol = await loop.create_connection(factory, "192.168.4.1", 23)

    try:
        async for line, ts in TCPTransportLineIterator(protocol):
            print("Received:", repr(line), "at", ts)
    except Exception as e:
        print("Connection closed or error:", e)
    finally:
        transport.close()



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







class SerialLineIterator:
    """Async iterator over line-terminated text from an AioSerial instance."""

    def __init__(self, ser: aioserial.AioSerial,
                 encoding: str = "utf-8",
                 errors: str = "replace",
                 limit: int | None = None) -> None:
        """
        ser:     an already opened aioserial.AioSerial
        encoding/errors: passed to bytes.decode
        limit:   max number of lines to yield (None = infinite)
        """
        self._ser = ser
        self._encoding = encoding
        self._errors = errors
        self._limit = limit
        self._count = 0
        self._closed = False

    def __aiter__(self):
        # The iterator is its own async iterator.
        return self

    async def __anext__(self) -> str:
        if self._closed:
            raise StopAsyncIteration

        if self._limit is not None and self._count >= self._limit:
            raise StopAsyncIteration

        # Read one line (bytes) from the serial port.
        # aioserial provides readline_async which reads until LF by default. [web:1]
        data: bytes = await self._ser.readline_async()
        if not data:
            # EOF / port closed: stop iteration
            self._closed = True
            raise StopAsyncIteration

        self._count += 1
        # Decode to string and return.
        return data.decode(self._encoding, errors=self._errors)



async def main():
    ser = aioserial.AioSerial(port="/dev/ttyUSB0", baudrate=115200)  # [web:1]
    async for line in SerialLineIterator(ser):
        print("got line:", line.rstrip("\r\n"))
        # Optionally break on some condition
        if line.strip() == "QUIT":
            break

    ser.close()

asyncio.run(main())
