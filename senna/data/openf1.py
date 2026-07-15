"""OpenF1 REST client — historical enrichment only, free tier respected.

Real-time OpenF1 is paid and 2022 does not exist there (F-11); every request
is throttled through a token bucket at the AR-15 rate and backs off on 429/5xx.
Config arrives as the `openf1` section of configs/ingest.yaml and is resolved
through senna.config.get so a null constant raises instead of flowing through.
"""

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx

from senna.config import get
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
        self._first_season = get(cfg, "first_season")
        self._max_retries = get(cfg, "max_retries")
        self._backoff_base_s = get(cfg, "backoff_base_s")
        self._backoff_factor = get(cfg, "backoff_factor")
        self._backoff_cap_s = get(cfg, "backoff_cap_s")
        self._sleep = sleep
        self._bucket = TokenBucket(
            rate_rps=get(cfg, "rate_limit_rps"),
            burst=get(cfg, "burst"),
            clock=clock,
            sleep=sleep,
        )
        self._http = httpx.Client(base_url=get(cfg, "base_url"), transport=transport)

    def get(self, endpoint: str, **params) -> list[dict]:
        year = params.get("year")
        if year is not None and year < self._first_season:
            raise OpenF1YearError(
                f"OpenF1 starts in {self._first_season}; "
                f"{year} must come from FastF1 alone (F-11)"
            )

        for attempt in range(self._max_retries + 1):
            self._bucket.acquire()
            response = self._http.get(endpoint, params=params)
            if response.status_code not in RETRYABLE_STATUSES:
                response.raise_for_status()
                return response.json()
            if attempt == self._max_retries:
                response.raise_for_status()
            backoff_s = min(
                self._backoff_base_s * self._backoff_factor**attempt,
                self._backoff_cap_s,
            )
            self._sleep(backoff_s)

        raise AssertionError("unreachable: the last attempt either returned or raised")

    def pit(self, session_key: int) -> list[dict]:
        return self.get("pit", session_key=session_key)

    def stints(self, session_key: int) -> list[dict]:
        return self.get("stints", session_key=session_key)

    def close(self) -> None:
        self._http.close()


def match_session(rows: list[dict], date_utc, session_name: str) -> dict | None:
    """Find the /sessions row for a FastF1 session by name and UTC date.

    OpenF1 stamps date_start with an offset and races can slip past UTC
    midnight (Vegas starts late Saturday local), so the scheduled and actual
    dates may differ — match on the UTC day with one day of tolerance.
    """
    by_day = {}
    for row in rows:
        if row.get("session_name") != session_name or not row.get("date_start"):
            continue
        start = datetime.fromisoformat(row["date_start"])
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        by_day[start.astimezone(UTC).date()] = row

    target = date_utc.date()
    for offset_days in (0, 1, -1):
        match = by_day.get(target + timedelta(days=offset_days))
        if match is not None:
            return match
    return None
