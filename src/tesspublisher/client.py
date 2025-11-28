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
from . import transport, logger


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

# ------------------------------------
# Signal handling for the whole server
# ------------------------------------


def signal_pause():
    pub.sendMessage(Topic.CLIENT_PAUSE)


def signal_resume():
    pub.sendMessage(Topic.CLIENT_RESUME)


def signal_reload():
    pub.sendMessage(Topic.CLIENT_RELOAD)


signal.signal(signal.SIGHUP, signal_reload)
signal.signal(signal.SIGUSR1, signal_pause)
signal.signal(signal.SIGUSR2, signal_resume)

# ------------------
# Auxiliar functions
# ------------------


# Either coming from HTTP API or the Signal interface
def on_client_reload() -> None:
    state.reloaded = True


pub.subscribe(on_client_reload, Topic.CLIENT_RELOAD)


# -----------------------
# The reload monitor task
# -----------------------


def load_config(path: str) -> dict[str, Any]:
    with open(path, "rb") as config_file:
        return tomllib.load(config_file)


async def reload_file(path: str) -> dict[str, Any]:
    global state
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, load_config, path)


async def reload_monitor() -> None:
    """Config file reload monitoring task"""
    while True:
        if state.reloaded:
            state.reloaded = False
            log.warning("reloading server configuration")
            options = await reload_file(state.config_path)
            mqtt.on_client_reload(options["mqtt"])
            http.on_client_reload(options["http"])
        await asyncio.sleep(1)


def get_photometers_info(config_options: Mapping) -> list[Tuple[str, PhotometerInfo]]:
    return [
        (
            info["endpoint"],
            info["period"],
            info["log_level"],
            # PhotometerInfo validates input data from config.toml
            PhotometerInfo(
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
            ),
        )
        for name, info in state.options["tess"].items()
        if name.lower().startswith("stars")
    ]


# ================
# MAIN ENTRY POINT
# ================


async def cli_main(args: Namespace) -> None:
    global state
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGHUP, signal_reload)
    loop.add_signal_handler(signal.SIGUSR1, signal_pause)
    loop.add_signal_handler(signal.SIGUSR2, signal_resume)
    state.config_path = args.config
    state.options = load_config(state.config_path)
    state.queue = asyncio.PriorityQueue(maxsize=state.options["tess"]["qsize"])
    photometers = get_photometers_info(state.options["tess"].items())
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(reload_monitor())
            tg.create_task(http.admin(state.options["http"]))
            tg.create_task(mqtt.publisher(state.options["mqtt"], state.queue))
            for endpoint, period, log_level, info in photometers:
                log = logging.getLogger(info.name)
                log_level = logger.level(log_level)
                log.setLevel(log_level)
                comm = await transport.factory(endpoint=endpoint, logger=log)
                phot = Photometer(
                    comm=comm, period=period, info=info, mqtt_queue=state.queue, logger=log
                )
                tg.create_task(phot.reader())
                tg.create_task(phot.sampler())
    except* KeyError as e:
        log.exception("%s -> %s", e, e.__class__.__name__)
    except* asyncio.CancelledError:
        pass


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
