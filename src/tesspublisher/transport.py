import asyncio
import logging
from logging import Logger
from datetime import datetime, timezone
from typing import Any, Tuple, Union

import aioserial
import serial


def chop(endpoint: str, sep=":"):
    """Chop a list of strings, separated by sep and
    strips individual string items from leading and trailing blanks"""
    chopped = tuple(elem.strip() for elem in endpoint.split(sep))
    if len(chopped) == 1 and chopped[0] == "":
        chopped = tuple()
    return chopped


class SerialTransport:
    def __init__(self, logger: Logger, port="/dev/ttyUSB0", baudrate=9600):
        self.log = logger
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
        self.log.info(data)
        return data, now


class TCPTransport(asyncio.Protocol):
    def __init__(
        self,
        logger: Logger,
        host: str = "192.168.4.1",
        port: int = 23,
        loop: asyncio.AbstractEventLoop | None = None,
        encoding: str = "utf-8",
        newline: bytes = b"\n",
    ) -> None:
        self.loop = loop or asyncio.get_event_loop()
        self.log = logger
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

    async def open(self) -> None:
        transport, self.protocol = await self.loop.create_connection(
            lambda: self, self.host, self.port
        )

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
            message = line.decode(self.encoding, errors="replace")

            if (
                self.on_data_received is not None
                and not self.on_data_received.cancelled()
                and not self.on_data_received.done()
            ):
                self.on_data_received.set_result((message, now))
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


async def factory(endpoint: str, logger: Logger) -> Union[TCPTransport, SerialTransport]:
    proto, A, B = chop(endpoint)
    if proto == "serial":
        transport = SerialTransport(logger=logger, port=A, baudrate=B)

    elif proto == "tcp":
        transport = TCPTransport(logger=logger, host=A, port=B)

    else:
        raise NotImplementedError(f"Unsupported protocol: {proto}")
    return transport
