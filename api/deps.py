"""Request-scoped access to what the lifespan owns. Routes reach the engine and
redis through request.app.state, so tests and deploys swap them by construction —
there is no module-level connection anywhere in the API process (F-26).
"""

import os
from functools import cache

from fastapi import Request

from senna import config


@cache
def serving_config() -> dict:
    return config.load("serving")


def redis_url() -> str:
    url = os.environ.get("REDIS_URL")
    if not url:
        raise RuntimeError(
            "REDIS_URL is not set — start `docker compose up redis` and export it "
            "(compose and Railway both inject it; see .env.example)"
        )
    return url


def engine(request: Request):
    return request.app.state.engine


def redis_client(request: Request):
    return request.app.state.redis


def rq_queue(request: Request):
    return request.app.state.queue
