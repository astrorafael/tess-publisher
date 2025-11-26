# ----------------------------------------------------------------------
# Copyright (c) 2025 Rafael Gonzalez.
#
# See the LICENSE file for details
# ----------------------------------------------------------------------

# --------------------
# System wide imports
# -------------------

import json
import asyncio
import logging

from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Optional, Union

# ---------------------------
# Third-party library imports
# ----------------------------


import decouple
from pydantic import ValidationError
import aiomqtt
from aiomqtt.client import ProtocolVersion
from pubsub import pub

# --------------
# local imports
# -------------

from . import logger
from .constants import Topic, MessagePriority


# ---------
# CONSTANTS
# ---------


# ------------------
# Additional Classes
# ------------------


@dataclass(slots=True)
class Stats:
    num_published: int = 0
    num_readings: int = 0
    num_register: int = 0
    num_filtered: int = 0

    def reset(self) -> None:
        """Resets stat counters"""
        self.num_published = 0
        self.num_readings = 0
        self.num_register = 0
        self.num_filtered = 0

    def show(self) -> None:
        log.info(
            "MQTT Stats [Total, Reads, Register, Discarded] = %s",
            [stats.num_published, stats.num_readings, stats.num_register, stats.num_filtered],
        )


@dataclass(slots=True)
class State:
    transport: str = decouple.config("MQTT_TRANSPORT")
    host: str = decouple.config("MQTT_HOST")
    port: int = decouple.config("MQTT_PORT", cast=int)
    username: str = decouple.config("MQTT_USERNAME")
    password: int = decouple.config("MQTT_PASSWORD")
    client_id: str = decouple.config("MQTT_CLIENT_ID")
    keepalive: int = 60
    topic_register: str = decouple.config("MQTT_TOPIC")
    topics: list[str] = field(default_factory=list)
    log_level: int = 0
    protocol_log_level: int = 0

    def update(self, options: dict[str, Any]) -> None:
        """Updates the mutable state"""

        self.keepalive = options["keepalive"]
        self.log_level = logger.level(options["log_level"])
        log.setLevel(self.log_level)
        self.protocol_log_level = logger.level(options["protocol_log_level"])
        proto_log.setLevel(self.protocol_log_level)


# ----------------
# Global variables
# ----------------

log = logging.getLogger(logger.LogSpace.MQTT.value)
proto_log = logging.getLogger("MQTT")
stats = Stats()
state = State()

# -----------------
# Auxiliar functions
# ------------------


def on_server_stats() -> None:
    global state
    stats.show()
    stats.reset()


pub.subscribe(on_server_stats, Topic.CLIENT_STATS)


def on_server_reload(options: dict[str, Any]) -> None:
    global state
    state.update(options)


# Do not subscribe. server.on_server_reload() will call us
# pub.subscribe(on_server_reload, Topic.CLIENT_RELOAD)


# --------------
# The MQTT task
# --------------


async def publisher(options: dict[str, Any], queue: asyncio.PriorityQueue) -> None:
    interval = 5
    state.update(options)
    log.setLevel(state.log_level)
    client = aiomqtt.Client(
        state.host,
        state.port,
        username=state.username,
        password=state.password,
        identifier=state.client_id,
        logger=proto_log,
        transport=state.transport,
        keepalive=state.keepalive,
        protocol=ProtocolVersion.V311,
    )
    while True:
        try:
            async with client:
                priority, item = await queue.get()
                if priority == MessagePriority.MQTT_REGISTER:
                    await client.publish("STARS4ALL/register", payload=json.dumps(item))
                else:
                    name = item["name"]
                    await client.publish(f"STARS4ALL/{name}/reading", payload=json.dumps(item))
        except aiomqtt.MqttError:
            log.warning(f"Connection lost; Reconnecting in {interval} seconds ...")
            await asyncio.sleep(interval)
        except Exception as e:
            log.critical("Unexpected & unhandled exception, see details below")
            log.exception(e)
