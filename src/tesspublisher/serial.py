# ----------------------------------------------------------------------
# Copyright (c) 2025 Rafael Gonzalez.
#
# See the LICENSE file for details
# ----------------------------------------------------------------------

import json
import logging
import asyncio
from datetime import datetime, timezone, timedelta

import aioserial
import serial

from .logger import LogSpace
from .constants import MessagePriority
from .model import PhotometerInfo

# ----------------
# Global variables
# ----------------

log = logging.getLogger(LogSpace.SERIAL.value)


async def do_register(phot: PhotometerInfo, queue: asyncio.PriorityQueue) -> None:
    await queue.put((MessagePriority.MQTT_REGISTER, phot.to_mqtt()))
    await asyncio.sleep(5)
    await queue.put((MessagePriority.MQTT_REGISTER, phot.to_mqtt()))


async def reader(port, phot: PhotometerInfo, queue: asyncio.PriorityQueue) -> None:
    try:
        serial_obj = aioserial.AioSerial(port=port, baudrate=9600)
    except serial.serialutil.SerialException as e:
        log.error(e)
        return
    log.info("Using %s for %s", port, phot.name)
    do_register(phot, queue)
    while True:
        try:
            payload = await serial_obj.readline_async()
            now = datetime.now(timezone.utc)
            if len(payload):
                payload = json.loads(payload)
                payload["tstamp"] = (now + timedelta(seconds=0.5)).strftime("%Y-%m-%dT%H:%M:%S")
                payload = json.dumps(payload)
                await queue.put((MessagePriority.MQTT_READINGS, payload))
        except Exception as e:
            log.exception(e)

