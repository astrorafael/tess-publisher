# ----------------------------------------------------------------------
# Copyright (c) 2025
#
# See the LICENSE file for details
# see the AUTHORS file for authors
# ----------------------------------------------------------------------

from enum import Enum, StrEnum

import logging
from typing import Annotated
from pydantic import BaseModel, AfterValidator

from .model import Stars4AllName


class Levels(Enum):
    none = logging.NOTSET
    critical = logging.CRITICAL
    error = logging.ERROR
    warn = logging.WARNING
    info = logging.INFO
    debug = logging.DEBUG
    trace = 5


STR_TO_LEVEL = {lev.name: lev.value for lev in Levels}


def level(level_str: str) -> int:
    return STR_TO_LEVEL[level_str]


def level_name(level: int) -> str:
    return Levels(level).name


# Log NameSpaces
class LogSpace(StrEnum):
    MQTT = "mqtt"
    HTTP = "http"
    CLIENT = "client"


# ------------------------
# This is for the HTTP API
# ------------------------


def is_log_level(value: str) -> str:
    if value not in STR_TO_LEVEL.keys():
        raise ValueError(f"log level {value} outside {STR_TO_LEVEL.keys()} values")
    return value


def is_log_name(value: str) -> str:
    allowed = [x.value for x in LogSpace]
    if value not in allowed:
        raise ValueError(f"log level {value} outside {allowed} values")
    return value


LogLevel = Annotated[str, AfterValidator(is_log_level)]
LogSpaceName = Annotated[str, AfterValidator(is_log_name)]


class PhotLogLevelInfo(BaseModel):
    name: Stars4AllName
    level: LogLevel


class LogLevelInfo(BaseModel):
    name: LogSpaceName
    level: LogLevel
