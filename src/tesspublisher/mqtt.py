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

from tessdbdao import PhotometerModel, TimestampSource, RegisterState
from tessdbapi.model import PhotometerInfo, ReadingInfo1c, ReadingInfo4c

# --------------
# local imports
# -------------

from . import logger
from .constants import MessagePriority, Topic


# ---------
# CONSTANTS
# ---------

TESS4C_FILTER_KEYS = ("F1", "F2", "F3", "F4")

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
    topic_register: str = ""
    topics: list[str] = field(default_factory=list)
    white_list: list[str] = field(default_factory=list)
    black_list: list[str] = field(default_factory=list)
    log_level: int = 0
    protocol_log_level: int = 0

    def update(self, options: dict[str, Any]) -> None:
        """Updates the mutable state"""
        self.topics = options["tess_topics"]
        self.topic_register = options["tess_topic_register"]
        self.keepalive = options["keepalive"]
        self.white_list = options["tess_whitelist"]
        self.black_list = options["tess_blacklist"]
        self.log_level = logger.level(options["log_level"])
        log.setLevel(self.log_level)
        self.protocol_log_level = logger.level(options["protocol_log_level"])
        log.setLevel(self.protocol_log_level)


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


def is_tess4c_payload(row: dict[str, Any]) -> bool:
    return "F4" in row


def _remap_tess4c_reading(row: dict[str, Any]) -> None:
    """Flatten the JSON structure for further processing"""
    for i, filt in enumerate(TESS4C_FILTER_KEYS, 1):
        for key, value in row[filt].items():
            row[f"{key}{i}"] = value
    for filt in TESS4C_FILTER_KEYS:
        del row[filt]


def _remap_tess4c_register(row: dict[str, Any]) -> None:
    """Flatten the JSON structure for further processing"""
    for i, filt in enumerate(TESS4C_FILTER_KEYS, 1):
        for key, value in row[filt].items():
            row[f"{key}{i}"] = value
    for filt in TESS4C_FILTER_KEYS:
        del row[filt]
    row["model"] = PhotometerModel.TESS4C


def _remap_tessw_reading(row: dict[str, Any]):
    """remaps keywords for the filter/database statges"""
    row["mag1"] = row["mag"]
    row["freq1"] = row["freq"]
    del row["mag"]
    del row["freq"]


def _remap_tessw_register(row: dict[str, Any]):
    """remaps keywords for the filter/database statges"""
    row["calib1"] = row["calib"]
    del row["calib"]
    row["offsethz1"] = row.get("offsethz", 0.0)
    if "offsethz" in row:
        del row["offsethz"]
    row["model"] = PhotometerModel.TESSW


def _handle_reading(
    row: dict[str, Any], now: Optional[datetime], src: TimestampSource
) -> Union[None, ReadingInfo1c, ReadingInfo4c]:
    """
    Handle actual reqadings data coming from onum_published()
    """
    global stats
    stats.num_readings += 1
    info = None
    try:
        if is_tess4c_payload(row):
            _remap_tess4c_reading(row)
            info = ReadingInfo4c(
                tstamp=now,
                tstamp_src=src,
                name=row["name"],
                sequence_number=row["seq"],
                box_temperature=row.get("tamb"),
                sky_temperature=row.get("tsky"),
                signal_strength=row["wdBm"],
                hash=row.get("hash"),
                freq1=row["freq1"],
                mag1=row["mag1"],
                freq2=row["freq2"],
                mag2=row["mag2"],
                freq3=row["freq3"],
                mag3=row["mag3"],
                freq4=row["freq4"],
                mag4=row["mag4"],
            )
        else:
            _remap_tessw_reading(row)
            info = ReadingInfo1c(
                tstamp=now,
                tstamp_src=src,
                name=row["name"],
                sequence_number=row["seq"],
                box_temperature=row["tamb"],
                sky_temperature=row["tsky"],
                signal_strength=row["wdBm"],
                hash=row.get("hash"),
                freq1=row["freq1"],
                mag1=row["mag1"],
            )

    except ValidationError as e:
        log.error("Validation error in readings payload: %s", row)
        log.error(e)
        for v in e.errors():
            log.error(v)
    except KeyError as e:
        log.info("Missing payload field in %s", row)
        log.error(e)
    except Exception as e:
        log.error("Unexpected exception when dealing with readings %s. Stack trace follows:", row)
        log.error(e)
    return info


def _handle_register(
    row: dict[str, Any], now: Optional[datetime], src: TimestampSource
) -> Optional[PhotometerInfo]:
    """
    Handle registration data coming from onum_published()
    """
    global stats
    plog = logging.getLogger(row["name"])
    stats.num_register += 1
    # 'now' is usualy None, so we don't log it
    log.info("Register message: %s", row)
    plog.debug("Register message: %s", row)
    info = None
    compilation_date = row.get("date")
    if not compilation_date:
        row["firmware"] = row.get("firmware")
    else:
        row["firmware"] = f"{row.get('firmware')} ({compilation_date})"
    try:
        if is_tess4c_payload(row):
            _remap_tess4c_register(row)
            info = PhotometerInfo(
                name=row["name"],
                mac_address=row["mac"],
                model=PhotometerModel.TESS4C,
                authorised=False,
                registered=RegisterState.AUTO,
                firmware=row["firmware"],
                zp1=row["calib1"],
                filter1=row["band1"],
                offset1=row.get("offsethz1", 0),
                zp2=row["calib2"],
                filter2=row["band2"],
                offset2=row.get("offsethz2", 0),
                zp3=row["calib3"],
                filter3=row["band3"],
                offset3=row.get("offsethz3", 0),
                zp4=row["calib4"],
                filter4=row["band4"],
                offset4=row.get("offsethz4", 0),
                tstamp=now,
                tstamp_src=src,
            )
        else:
            _remap_tessw_register(row)
            info = PhotometerInfo(
                name=row["name"],
                mac_address=row["mac"],
                model=PhotometerModel.TESSW,
                # firmware="0.1.0",
                authorised=False,
                registered=RegisterState.AUTO,
                firmware=row.get("firmware"),
                zp1=row["calib1"],
                filter1=row.get("filter1", "UV/IR-740"),
                offset1=row["offsethz1"],
                tstamp=now,
                tstamp_src=src,
            )
    except ValidationError as e:
        log.error("Validation error in registration payload: %s", row)
        for v in e.errors():
            log.error(v)
    except KeyError as e:
        log.error("Missing payload field in %s", row)
        log.error(e)
    except Exception as e:
        log.error(
            "Unexpected exception when dealing with registration %s. Stack trace follows:", row
        )
        log.exception(e)
    return info


# --------------
# The MQTT task
# --------------


async def subscriber(
    options: dict[str, Any], filt_queue: asyncio.Queue, db_queue: asyncio.PriorityQueue
) -> None:
    global stats
    global state
    interval = 5
    state.update(options)
    log.setLevel(state.log_level)
    proto_log.setLevel(state.protocol_log_level)
    log.info("Starting MQTT subscriber")
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
                log.info("subscribing to %s", state.topic_register)
                await client.subscribe(state.topic_register, qos=2)
                for topic in state.topics:
                    log.info("subscribing to %s", topic)
                    await client.subscribe(topic, qos=2)
                async for message in client.messages:
                    try:
                        stats.num_published += 1
                        payload = message.payload.decode("utf-8")
                        row = json.loads(payload)
                        if "tstamp" not in row:
                            tstamp, tsmap_src = None, TimestampSource.SUBSCRIBER
                        else:
                            tstamp, tsmap_src = row["tstamp"], TimestampSource.PUBLISHER
                        plog = logging.getLogger(row["name"])
                        # Discard retained messages to avoid duplicates in the database
                        if message.retain:
                            plog.debug("Discarded payload by retained flag")
                            stats.num_filtered += 1
                            continue
                        # Apply White List filter
                        if state.white_list and row["name"] not in state.white_list:
                            plog.debug("Discarded payload by whitelist")
                            stats.num_filtered += 1
                            continue
                        # Apply Black List filter
                        if state.black_list and row["name"] in state.black_list:
                            plog.debug("Discarded payload by blacklist")
                            stats.num_filtered += 1
                            continue
                        # Handle registering
                        if message.topic.matches(state.topic_register):
                            info = _handle_register(row, tstamp, tsmap_src)
                            if info:
                                if not db_queue.full():
                                    db_queue.put_nowait((MessagePriority.REGISTER, info))
                                else:
                                    log.warning("Register DBQueue full: %s", dict(info))
                        else:
                            info = _handle_reading(row, tstamp, tsmap_src)
                            if info:
                                filt_queue.put_nowait(info)
                    except json.JSONDecodeError:
                        log.error("Invalid JSON in payload=%s", payload)
                    except asyncio.QueueFull:
                        log.error("Queue full for %s", row)
        except aiomqtt.MqttError:
            log.warning(f"Connection lost; Reconnecting in {interval} seconds ...")
            await asyncio.sleep(interval)
        except Exception as e:
            log.critical("Unexpected & unhandled exception, see details below")
            log.exception(e)
