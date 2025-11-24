# ----------------------------------------------------------------------
# Copyright (c) 2022
#
# See the LICENSE file for details
# see the AUTHORS file for authors
# ----------------------------------------------------------------------

from enum import StrEnum, IntEnum


class MessagePriority(IntEnum):
    """Priority of messages coming from the MQTT broker or the HTTP admin interface"""
    REGISTER = 1
    MQTT_READINGS = 2
  
class Topic(StrEnum):
    CLIENT_STATS = "client.stats"
    CLIENT_RELOAD = "client.reload"
    CLIENT_PAUSE = "client.pause"
    CLIENT_RESUME = "client.resume"


DEFAULT_FILTER = "UV/IR-740"
DEFAULT_AZIMUTH = 0.0
DEFALUT_ALTITUDE = 90.0
DEFAULT_FOV = 17.0
DEFAULT_OFFSET_HZ = 0.0

UNKNOWN = "Unknown"
