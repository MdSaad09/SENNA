"""Request-scoped access to what the lifespan owns. Routes reach the engine through
request.app.state, so tests and deploys swap it by construction — there is no
module-level connection anywhere in the API process.
"""

from functools import cache

from fastapi import Request

from senna import config


@cache
def serving_config() -> dict:
    return config.load("serving")

def engine(request: Request):
    return request.app.state.engine


