"""Client-side rate limiting so bulk ingest never hammers a free service (E-12)."""

from typing import Callable


class TokenBucket:
    """Blocks in acquire() until a token is free. Clock and sleep are injected
    so tests can run on virtual time."""

    def __init__(
        self,
        rate_rps: float,
        burst: int,
        clock: Callable[[], float],
        sleep: Callable[[float], None],
    ) -> None:
        self.rate_rps = rate_rps
        self.burst = burst
        self._clock = clock
        self._sleep = sleep
        self._tokens = float(burst)
        self._refilled_at = clock()

    def _refill(self) -> None:
        now = self._clock()
        self._tokens = min(
            float(self.burst), self._tokens + (now - self._refilled_at) * self.rate_rps
        )
        self._refilled_at = now

    def acquire(self) -> None:
        self._refill()
        if self._tokens < 1.0:
            self._sleep((1.0 - self._tokens) / self.rate_rps)
            self._refill()
        self._tokens -= 1.0
