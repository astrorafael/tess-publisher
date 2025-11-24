# ----------------------------------------------------------------------
# Copyright (c) 2025 Rafael Gonzalez.
#
# See the LICENSE file for details
# ----------------------------------------------------------------------

# --------------------
# System wide imports
# -------------------

import logging
from typing import Any
from dataclasses import dataclass, asdict

# ---------------------------
# Third-party library imports
# ----------------------------

import decouple
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pubsub import pub

from .model import Stars4AllName


# --------------
# local imports
# -------------

from .logger import (
    PhotLogLevelInfo,
    LogLevelInfo,
    level,
    LogSpace,
    LogSpaceName,
    level_name,
)
from .constants import Topic


# -------
# Classes
# -------


@dataclass(slots=True)
class State:
    host: str = decouple.config("ADMIN_HTTP_LISTEN_ADDR")
    port: int = decouple.config("ADMIN_HTTP_PORT", cast=int)
    log_level: int = 0

    def update(self, options: dict[str, Any]) -> None:
        """Updates the mutable state"""
        self.log_level = level(options["log_level"])



# ----------------
# Global variables
# ----------------

log = logging.getLogger(LogSpace.HTTP.value)

app = FastAPI()
state = State()


def on_server_reload(options: dict[str, Any]) -> None:
    global state
    state.update(options)


# Do not subscribe. server.on_server_reload() will call us
# pub.subscribe(on_server_reload, Topic.CLIENT_RELOAD)


# -------------------------
# The HTTP server main task
# -------------------------


async def admin(options: dict[str, Any]) -> None:
    global state
    state.update(options)
    log.setLevel(state.log_level)
    config = uvicorn.Config(
        f"{__name__}:app",
        host=state.host,
        port=state.port,
        log_level="error",
        use_colors=False,
    )
    server = uvicorn.Server(config)
    await server.serve()


# ======================
# HTTP FastAPI ENDPOINTS
# ======================


@app.get("/v1")
async def root():
    log.info("Received hello request")
    return {"message": "I'm alive"}


@app.post("/v1/client/reload")
async def server_reload():
    log.info("reload configuration request")
    pub.sendMessage(Topic.CLIENT_RELOAD)
    return {"message": "Server reloaded"}


@app.post("/v1/client/pause")
def server_pause():
    log.info("client paused")
    pub.sendMessage(Topic.CLIENT_PAUSE)
    return {"message": "Server paused operation"}


@app.post("/v1/client/resume")
def server_resume():
    log.info("client resumed")
    pub.sendMessage(Topic.CLIENT_RESUME)
    return {"message": "Server resumed operation"}


# ===============
# TASK LOGGER API
# ===============


@app.get("/v1/loggers")
def loggers():
    log.info("task loggers list request")
    response = [
        {"name": x.value, "level": level_name(logging.getLogger(x.value).level)} for x in LogSpace
    ]
    log.info("task loggers list request returns %s", response)
    return response


@app.get("/v1/loggers/{name}")
def get_logger_level(name: LogSpaceName):
    level = level_name(logging.getLogger(name).level)
    response = LogLevelInfo(name=name, level=level)
    log.info("task logger get level request returns %s", response)
    return response


@app.put("/v1/loggers/{name}")
def set_logger_level(name: LogSpaceName, log_level_info: LogLevelInfo):
    log.info("task logger set level request: %s", log_level_info)
    logging.getLogger(name).setLevel(level(log_level_info.level))
    return log_level_info


# ================================
# INDIVIFUAL PHOTOMETER LOGGER API
# ================================


@app.get("/v1/ploggers")
def ploggers():
    result = [
        {"name": name, "level": level_name(logging.getLogger(name).level)}
        for name in Sampler.instances.keys()
    ]
    response = sorted(result, key=lambda x: x["name"])
    log.info("photometer loggers list request returns %s", response)
    return response


@app.get("/v1/ploggers/{name}")
def get_plogger_level(name: Stars4AllName):
    if name in Sampler.instances.keys():
        level = level_name(logging.getLogger(name).level)
        response = PhotLogLevelInfo(name=name, level=level)
        log.info("photometers logger get level request returns %s", response)
    else:
        raise HTTPException(status_code=404, detail=f"Logger {name} not yet available")
    return response


@app.put("/v1/ploggers/{name}")
def set_plogger_level(name: Stars4AllName, log_level_info: PhotLogLevelInfo):
    global state
    log.info("photometers logger set level request: %s", log_level_info)
    if log_level_info.name in Sampler.instances.keys():
        plog = logging.getLogger(log_level_info.name)
        plog.setLevel(level(log_level_info.level))
        return log_level_info
    else:
        log.info("Logger %s not yet available", log_level_info.name)
        raise HTTPException(
            status_code=404, detail=f"Logger {log_level_info.name} not yet available"
        )
