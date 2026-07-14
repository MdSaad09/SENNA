import pytest

from senna.data.throttle import TokenBucket

RATE_RPS = 3.0  # openf1.rate_limit_rps (sourced AR-15: free tier ~3 req/s)
BURST = 3  # openf1.burst (stylised)


def _bucket(virtual_clock) -> TokenBucket:
    return TokenBucket(
        rate_rps=RATE_RPS,
        burst=BURST,
        clock=virtual_clock.read,
        sleep=virtual_clock.sleep,
    )


def test_an_initial_burst_goes_through_instantly_then_steady_state(virtual_clock):
    bucket = _bucket(virtual_clock)

    stamps = []
    for _ in range(BURST + 3):
        bucket.acquire()
        stamps.append(virtual_clock.read())

    assert stamps[:BURST] == [0.0] * BURST
    # once the bucket is drained, tokens arrive one per 1/rate seconds
    assert stamps[BURST] == pytest.approx(1 / RATE_RPS)
    assert stamps[BURST + 1] == pytest.approx(2 / RATE_RPS)


def test_the_observed_rate_never_exceeds_the_configured_rate(virtual_clock):
    bucket = _bucket(virtual_clock)

    stamps = []
    for _ in range(100):
        bucket.acquire()
        stamps.append(virtual_clock.read())

    # bucket invariant: k acquires beyond the burst need at least k/rate seconds,
    # measured from any starting acquire — E-12's guarantee against hammering Jolpica/OpenF1
    for i in range(len(stamps)):
        for j in range(i + 1, len(stamps)):
            assert stamps[j] - stamps[i] >= (j - i - BURST) / RATE_RPS - 1e-9
