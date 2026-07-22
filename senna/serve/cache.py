"""The E-15 cache key: sim:{model_version}:{env_hash}:{scenario_digest}:{seed}.

The scenario digest is the plan's divergence 1 — the 5.9.3 key as written collides
two circuits on the same seed. model_version and env_hash arrive from the served
triplet's manifest (never recomputed at serve time), so a retrain cold-starts its
own namespace by construction.
"""

import hashlib
import json
from functools import cache

from senna import config

_SCENARIO_FIELDS = ("circuit_id", "era", "grid_position", "weather_profile", "rival_band")


@cache
def _serving() -> dict:
    # the yaml is immutable per process; caching keeps file IO off the api's event
    # loop, where these helpers run inside async handlers
    return config.load("serving")


def sim_cache_key(model_version: str, env_hash: str, req) -> str:
    if req.seed is None:
        raise ValueError("seed must be drawn before the cache key is built — "
                         "two anonymous requests would otherwise share a 'None' key")
    scenario = {name: getattr(req, name) for name in _SCENARIO_FIELDS}
    digest = hashlib.sha256(
        json.dumps(scenario, sort_keys=True).encode()
    ).hexdigest()[:16]
    prefix = _serving()["cache"]["key_prefix"]
    return f"{prefix}:{model_version}:{env_hash}:{digest}:{req.seed}"


def ttl_seconds() -> int:
    return int(_serving()["cache"]["ttl_days"]) * 86_400


def events_channel(run_id: int) -> str:
    return f"{_serving()['channels']['events_prefix']}:{run_id}"
