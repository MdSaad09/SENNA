"""OpenF1 REST client — historical enrichment only, free tier respected.

Real-time OpenF1 is paid and 2022 does not exist there (F-11); every request
is throttled through a token bucket at the AR-15 rate and backs off on 429/5xx.
Config arrives as the `openf1` section of configs/ingest.yaml.
"""

import time
from collections.abc import Callable

import httpx

from senna.data.throttle import TokenBucket


class OpenF1YearError(ValueError):
    """OpenF1 has no data before its first season — use FastF1 alone there."""


RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


class OpenF1Client:
    def __init__(
        self,
        cfg: dict,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._cfg = cfg
        self._sleep = sleep
        self._bucket = TokenBucket(
            rate_rps=cfg["rate_limit_rps"], burst=cfg["burst"], clock=clock, sleep=sleep
        )
        self._http = httpx.Client(base_url=cfg["base_url"], transport=transport)

    def get(self, endpoint: str, **params) -> list[dict]:
        year = params.get("year")
        if year is not None and year < self._cfg["first_season"]:
            raise OpenF1YearError(
                f"OpenF1 starts in {self._cfg['first_season']}; "
                f"{year} must come from FastF1 alone (F-11)"
            )

        for attempt in range(self._cfg["max_retries"] + 1):
            self._bucket.acquire()
            response = self._http.get(endpoint, params=params)
            if response.status_code not in RETRYABLE_STATUSES:
                response.raise_for_status()
                return response.json()
            if attempt == self._cfg["max_retries"]:
                response.raise_for_status()
            backoff_s = min(
                self._cfg["backoff_base_s"] * self._cfg["backoff_factor"] ** attempt,
                self._cfg["backoff_cap_s"],
            )
            self._sleep(backoff_s)

        raise AssertionError("unreachable: the last attempt either returned or raised")

    def pit(self, session_key: int) -> list[dict]:
        return self.get("pit", session_key=session_key)

    def stints(self, session_key: int) -> list[dict]:
        return self.get("stints", session_key=session_key)
