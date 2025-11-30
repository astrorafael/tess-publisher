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
from dataclasses import dataclass

# ---------------------------
# Third-party library imports
# ----------------------------

import decouple
import uvicorn
from fastapi import FastAPI


# --------------
# local imports
# -------------

from .logger import level, LogSpace


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


# ===============
# TASK LOGGER API
# ===============
