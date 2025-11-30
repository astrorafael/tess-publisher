# ----------------------------------------------------------------------
# Copyright (c) 2025
#
# See the LICENSE file for details
# see the AUTHORS file for authors
# ----------------------------------------------------------------------

import re
import json
from datetime import datetime, timezone, timedelta
from typing import Annotated, Union, Optional
from pydantic import AfterValidator, BeforeValidator, BaseModel
from .constants import Model as PhotometerModel


ZP_LOW = 10
ZP_HIGH = 30

OFFSET_LOW = 0
OFFSET_HIGH = 1

STARS4ALL_NAME_PATTERN = re.compile(r"^stars\d{1,7}$")

# Sequence of possible timestamp formats
TSTAMP_FORMAT = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d %H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",  # timezone aware that must be converted to UTC
    "%Y-%m-%d %H:%M:%S%z",  # timezone aware that must be converted to UTC
)


def is_datetime(value: Union[str, datetime, None]) -> datetime:
    if value is None:
        return (datetime.now(timezone.utc) + timedelta(seconds=0.5)).replace(microsecond=0)
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError("tstamp must be a string or datetime.")
    for i, fmt in enumerate(TSTAMP_FORMAT):
        try:
            if i < 4:
                return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
            else:
                return datetime.strptime(value, fmt).astimezone(timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"{value} tstamp must be in one of {TSTAMP_FORMAT} formats.")


def is_mac_address(value: str) -> str:
    """'If this doesn't look like a MAC address at all, simple returns it.
    Otherwise properly formats it. Do not allow for invalid digits.
    """
    try:
        mac_parts = value.split(":")
        if len(mac_parts) != 6:
            raise ValueError("Invalid MAC: %s" % value)
        corrected_mac = ":".join(f"{int(x, 16):02X}" for x in mac_parts)
    except ValueError:
        raise ValueError("Invalid MAC: %s" % value)
    except AttributeError:
        raise ValueError("Invalid MAC: %s" % value)
    return corrected_mac


def is_valid_offset(value: float) -> float:
    if not (OFFSET_LOW <= value <= OFFSET_HIGH):
        raise ValueError(f"Freq. Offset {value} out of bounds [{OFFSET_LOW}-{OFFSET_HIGH}]")
    return value


def is_stars4all_name(value: str) -> str:
    value = value.lower()  # Make case-insensitive
    matchobj = STARS4ALL_NAME_PATTERN.match(value)
    if not matchobj:
        raise ValueError(f"name {value} is not a legal STARS4ALL name")
    return value


def is_zero_point(value: Union[str, int, float]) -> float:
    if isinstance(value, int):
        if not (ZP_LOW <= value <= ZP_HIGH):
            raise ValueError(f"Zero Point {value} out of bounds [{ZP_LOW}-{ZP_HIGH}]")
        return value
    elif isinstance(value, float):
        if not (ZP_LOW <= value <= ZP_HIGH):
            raise ValueError(f"Zero Point {value} out of bounds [{ZP_LOW}-{ZP_HIGH}]")
        return value
    elif isinstance(value, str):
        value = float(value)
        if not (ZP_LOW <= value <= ZP_HIGH):
            raise ValueError(f"Zero Point {value} out of bounds [{ZP_LOW}-{ZP_HIGH}]")
        return value
    raise ValueError(f"{value} has an unsupported type: {type(value)}")


def is_endpoint(value: str) -> str:
    return value


def is_log_level(value: str) -> str:
    levels = ("critical", "warn", "info", "debug", "none")
    if value not in levels:
        raise ValueError(f"log level not in {levels}")
    return value


def is_tx_period(value: int) -> int:
    if not (0 < value <= 86400):
        raise ValueError("Tx period not in range 0 < Tx <= 86400")
    return value


# --------------------

TxPeriodType = Annotated[int, AfterValidator(is_tx_period)]
LogLevelType = Annotated[str, AfterValidator(is_log_level)]
EndpointType = Annotated[str, AfterValidator(is_endpoint)]
Stars4AllName = Annotated[str, AfterValidator(is_stars4all_name)]
MacAddress = Annotated[str, AfterValidator(is_mac_address)]
FreqOffset = Annotated[float, AfterValidator(is_valid_offset)]
ZeroPointType = Annotated[Union[str, int, float], BeforeValidator(is_zero_point)]
TimestampType = Annotated[Union[str, datetime, None], BeforeValidator(is_datetime)]


class PhotometerInfo(BaseModel):
    endpoint: EndpointType
    log_level: LogLevelType
    period: TxPeriodType
    name: Stars4AllName
    mac_address: MacAddress
    model: PhotometerModel
    firmware: Optional[str] = None
    zp1: ZeroPointType
    filter1: str
    offset1: FreqOffset
    zp2: Optional[ZeroPointType] = None
    filter2: Optional[str] = None
    offset2: Optional[FreqOffset] = None
    zp3: Optional[ZeroPointType] = None
    filter3: Optional[str] = None
    offset3: Optional[FreqOffset] = None
    zp4: Optional[ZeroPointType] = None
    filter4: Optional[str] = None
    offset4: Optional[FreqOffset] = None

    def to_dict(self) -> str:
        if self.model == PhotometerModel.TESS4C:
            return {
                "rev": 3,
                "name": self.name,
                "mac": self.mac_address,
                "firmware": self.firmware,
                "F1": {"band": self.filter1, "calib": self.zp1},
                "F2": {"band": self.filter2, "calib": self.zp2},
                "F3": {"band": self.filter3, "calib": self.zp3},
                "F4": {"band": self.filter4, "calib": self.zp4},
            }
        elif self.model in (PhotometerModel.TESSW, PhotometerModel.TESSWDL):
            return {
                "name": self.name,
                "rev": 2,
                "mac": self.mac_address,
                "chan": "pruebas",
                "calib": self.zp1,
                "wdBm": 0,
            }
        else:
            raise ValueError(f"This photometer does not transmit: {PhotometerModel.TESSW.value}")


__all__ = ["PhotometerInfo"]
