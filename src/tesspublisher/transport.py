import asyncio
from logging import Logger
from typing import Union

import aioserial
import serial


class SerialTransport:
    def __init__(self, logger: Logger, port: str, baudrate: int):
        self.log = logger
        self.port = port
        self.baudrate = baudrate
        self.serial = None
        self.encoding: str = "utf-8"
        self.log.info("Using %s", self.__class__.__name__)

    async def open(self) -> None:
        try:
            self.serial = aioserial.AioSerial(port=self.port, baudrate=self.baudrate)
        except serial.serialutil.SerialException as e:
            self.log.error(e)
            raise
        else:
            self.log.info("Opening port %s", self.port)

    async def close(self) -> None:
        self.serial.close()

    def __aiter__(self) -> "SerialTransport":
        # The iterator is its own async iterator.
        return self

    async def __anext__(self) -> str:
        return (await self.serial.readline_async()).decode(self.encoding, errors="replace")


class TCPProtocol(asyncio.Protocol):
    def __init__(
        self,
        logger: Logger,
        host: str = "192.168.4.1",
        port: int = 23,
        loop: asyncio.AbstractEventLoop | None = None,
        encoding: str = "utf-8",
        newline: bytes = b"\r\n",
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
        self.log.info("Using %s", self.__class__.__name__)

    async def open(self) -> None:
        self.log.info("Opening TCP connection to (%s, %s)", self.host, self.port)
        transport, self.protocol = await self.loop.create_connection(
            lambda: self, self.host, self.port
        )

    async def close(self) -> None:
        self.transport.close()

    def __aiter__(self) -> "TCPProtocol":
        # The iterator is its own async iterator.
        return self

    async def __anext__(self) -> str:
        if self.on_data_received is not None and not self.on_data_received.done():
            self.on_data_received.cancel()
        self.on_data_received = self.loop.create_future()
        return await self.on_data_received

    # asyncio.Protocol callbacks
    def connection_made(self, transport: asyncio.Transport) -> None:
        self.log.info("Opened TCP connection to (%s, %s)", self.host, self.port)
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
            self._buffer = bytearray()  # Empties buffer
            message = line.decode(self.encoding, errors="replace")
            if (
                self.on_data_received is not None
                and not self.on_data_received.cancelled()
                and not self.on_data_received.done()
            ):
                self.on_data_received.set_result(message)
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
                ConnectionError("Connection lost before incoming message was complete")
            )


def chop(endpoint: str, sep=":"):
    """Chop a list of strings, separated by sep and
    strips individual string items from leading and trailing blanks"""
    chopped = tuple(elem.strip() for elem in endpoint.split(sep))
    if len(chopped) == 1 and chopped[0] == "":
        chopped = tuple()
    return chopped


async def factory(endpoint: str, logger: Logger) -> Union[TCPProtocol, SerialTransport]:
    proto, A, B = chop(endpoint)
    if proto == "serial":
        comm = SerialTransport(logger=logger, port=A, baudrate=B)
    elif proto == "tcp":
        comm = TCPProtocol(logger=logger, host=A, port=B)
    else:
        raise NotImplementedError(f"Unsupported protocol: {proto}")
    return comm
