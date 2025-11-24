# ----------------------------------------------------------------------
# Copyright (c) 2025
#
# See the LICENSE file for details
# see the AUTHORS file for authors
# ----------------------------------------------------------------------

import re
from typing import Annotated, Union
from pydantic import AfterValidator, BeforeValidator


ZP_LOW = 10
ZP_HIGH = 30

OFFSET_LOW = 0
OFFSET_HIGH = 1

STARS4ALL_NAME_PATTERN = re.compile(r"^stars\d{1,7}$")


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
    return ValueError(f"{value} has an unsupported type: {type(value)}")


# --------------------

Stars4AllName = Annotated[str, AfterValidator(is_stars4all_name)]
MacAddress = Annotated[str, AfterValidator(is_mac_address)]
FreqOffset = Annotated[float, AfterValidator(is_valid_offset)]
ZeroPointType = Annotated[Union[str, int, float], BeforeValidator(is_zero_point)]

__all__ = ["Stars4AllName"]
