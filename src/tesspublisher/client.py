# ----------------------------------------------------------------------
# Copyright (c) 2024 Rafael Gonzalez.
#
# See the LICENSE file for details
# ----------------------------------------------------------------------

# --------------------
# System wide imports
# -------------------

import asyncio
import logging
import tomllib
import signal

from logging import Logger
from dataclasses import dataclass
from typing import Any, Mapping, Tuple
from argparse import ArgumentParser, Namespace

# ---------------------------
# Third-party library imports
# ----------------------------


from lica.asyncio.cli import execute
from lica.validators import vfile

from pubsub import pub

# --------------
# local imports
# -------------

from . import __version__

# from .. import mqtt, http, dbase, stats, filtering
from . import http, mqtt
from .constants import Topic
from .logger import LogSpace
from .model import PhotometerInfo
from .photometer import Photometer


# The Server state
@dataclass(slots=True)
class State:
    config_path: str = None
    options: dict[str, Any] = None
    queue: asyncio.PriorityQueue = None
    reloaded: bool = False


# ----------------
# Global variables
# ----------------

log = logging.getLogger(LogSpace.CLIENT.value)
state = State()


# ------------------
# Auxiliar functions
# ------------------


def load_config(path: str) -> dict[str, Any]:
    with open(path, "rb") as config_file:
        return tomllib.load(config_file)


def get_photometers_info(config_options: Mapping) -> list[Tuple[str, PhotometerInfo]]:
    return [
        # PhotometerInfo validates input data from config.toml
        PhotometerInfo(
            endpoint=info["endpoint"],
            log_level=info["log_level"],
            period=info["period"],
            name=name,
            mac_address=info["mac_address"],
            model=info["model"],
            firmware=info.get("firmware"),
            zp1=info["zp1"],
            filter1=info["filter1"],
            offset1=info["offset1"],
            zp2=info.get("zp2"),
            filter2=info.get("filter2"),
            offset2=info.get("offset2"),
            zp3=info.get("zp3"),
            filter3=info.get("filter3"),
            offset3=info.get("offset3"),
            zp4=info.get("zp4"),
            filter4=info.get("filter4"),
            offset4=info.get("offset4"),
        )
        for name, info in state.options["tess"].items()
        if name.lower().startswith("stars")
    ]


# ================
# MAIN ENTRY POINT
# ================


async def cli_main(args: Namespace) -> None:
    global state
    state.config_path = args.config
    state.options = load_config(state.config_path)
    state.queue = asyncio.PriorityQueue(maxsize=state.options["tess"]["qsize"])
    phot_infos = get_photometers_info(state.options["tess"].items())
    photometers = [Photometer(info=info, mqtt_queue=state.queue) for info in phot_infos]
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(http.admin(state.options["http"]))
            tg.create_task(mqtt.publisher(state.options["mqtt"], state.queue))
            for phot in photometers:
                tg.create_task(phot.task())
    except* asyncio.TimeoutError:
        log.critical("No readings from any photometer. Program dies")
    except* KeyError as e:
        log.exception("%s -> %s", e, e.__class__.__name__)


def add_args(parser: ArgumentParser) -> None:
    parser.add_argument(
        "-c",
        "--config",
        type=vfile,
        required=True,
        metavar="<config file>",
        help="detailed .toml configuration file",
    )


def main():
    """The main entry point specified by pyproject.toml"""
    execute(
        main_func=cli_main,
        add_args_func=add_args,
        name=__name__,
        version=__version__,
        description="USB TESS publisher",
    )
