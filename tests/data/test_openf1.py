import httpx
import pytest

from senna.data.openf1 import OpenF1Client, OpenF1YearError

# mirrors the openf1 section of configs/ingest.yaml
OPENF1_CFG = {
    "base_url": "https://api.openf1.org/v1",  # sourced 5.3.3
    "first_season": 2023,  # sourced F-11 / AR-15: no 2022 coverage
    "rate_limit_rps": 3.0,  # sourced AR-15
    "burst": 3,  # stylised
    "max_retries": 5,  # stylised
    "backoff_base_s": 1.0,  # stylised
    "backoff_factor": 2.0,  # stylised
    "backoff_cap_s": 60.0,  # stylised
}


def _client(handler, virtual_clock) -> OpenF1Client:
    return OpenF1Client(
        OPENF1_CFG,
        transport=httpx.MockTransport(handler),
        clock=virtual_clock.read,
        sleep=virtual_clock.sleep,
    )


def test_a_year_before_first_season_raises_without_touching_the_network(virtual_clock):
    def handler(request):
        raise AssertionError("no request may leave the client for a pre-2023 year")

    client = _client(handler, virtual_clock)

    with pytest.raises(OpenF1YearError):
        client.get("sessions", year=2022)  # F-11: OpenF1 has nothing before 2023


def test_429_backs_off_exponentially_and_recovers(virtual_clock):
    pit_rows = [{"driver_number": 1, "lap_number": 14, "pit_duration": 21.4}]
    attempts = []

    def handler(request):
        attempts.append(str(request.url))
        if len(attempts) <= 2:
            return httpx.Response(429)
        return httpx.Response(200, json=pit_rows)

    client = _client(handler, virtual_clock)

    assert client.pit(session_key=9158) == pit_rows
    # burst (3) covers all three attempts, so every recorded sleep is backoff
    backoffs = virtual_clock.sleeps
    assert len(backoffs) == 2
    assert backoffs[0] >= OPENF1_CFG["backoff_base_s"]
    assert backoffs[1] >= OPENF1_CFG["backoff_base_s"] * OPENF1_CFG["backoff_factor"]
    assert max(backoffs) <= OPENF1_CFG["backoff_cap_s"]


def test_persistent_5xx_gives_up_after_max_retries(virtual_clock):
    attempts = []

    def handler(request):
        attempts.append(str(request.url))
        return httpx.Response(503)

    client = _client(handler, virtual_clock)

    with pytest.raises(httpx.HTTPStatusError):
        client.get("stints", session_key=9158)
    assert len(attempts) == OPENF1_CFG["max_retries"] + 1


def test_pit_and_stints_hit_their_endpoints_with_the_session_key(virtual_clock):
    seen = []

    def handler(request):
        seen.append((request.url.path, dict(request.url.params)))
        return httpx.Response(200, json=[])

    client = _client(handler, virtual_clock)
    client.pit(session_key=9158)
    client.stints(session_key=9158)

    assert seen == [
        ("/v1/pit", {"session_key": "9158"}),
        ("/v1/stints", {"session_key": "9158"}),
    ]


def test_every_request_is_throttled_through_the_token_bucket(virtual_clock):
    def handler(request):
        return httpx.Response(200, json=[])

    client = _client(handler, virtual_clock)
    for _ in range(9):
        client.get("pit", session_key=9158)

    # 9 requests at 3 req/s with a burst of 3 need at least 2 s of (virtual) waiting (E-12)
    floor_s = (9 - OPENF1_CFG["burst"]) / OPENF1_CFG["rate_limit_rps"]
    assert virtual_clock.now_s >= floor_s - 1e-9
