

from functools import cache

from fastapi import Request

from senna import config


@cache
def serving_config() -> dict:
    return config.load("serving")

def engine(request: Request):
    return request.app.state.engine


