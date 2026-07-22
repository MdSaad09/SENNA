"""Worker-process plumbing. Import this before anything heavy: torch and xgboost
each bundle their own OpenMP runtime, and two of them in one arm64 process segfault
once both do real work (the F09 landmine) — so the guard runs at import time, before
either library can load.
"""

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")

from senna import config  # noqa: E402


def redis_url() -> str:
    url = os.environ.get("REDIS_URL")
    if not url:
        raise RuntimeError(
            "REDIS_URL is not set — the worker needs the queue it was hired to drain "
            "(compose and Railway both inject it; see .env.example)"
        )
    return url


def queue_name() -> str:
    return config.load("serving")["queue"]["name"]
