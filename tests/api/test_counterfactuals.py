"""POST /counterfactuals: one POST answers with a linked pair — the agent's run and a
real-strategy replay baseline — both on 2024 physics. From F15 the agent leg runs the
era-matched 2024 model wherever its surrogate is baked; a root without the surrogate
degrades to the frozen 2026 headline with era_matched_model: pending-F14 recorded so
loudly no consumer can miss it (F-24, E-15). The pair is event-paired, not
seed-paired: the baseline's recorded EventTrace drives both twin rolls, so any
difference between the two frame streams is strategy, never luck (plan decision 2).
"""

import json
import os
import time

import pytest
import redis

from senna import config
from senna.serve.cache import events_channel
from senna.strategy.replay import RealStrategyReplay
from tests.api.conftest import (
    HAM_REAL_STOPS,
    RACE_ROUND,
    RACE_SEASON,
    SEED,
    drain_queue,
    seed_2024_bahrain,
)

# stand-in versions, deliberately not the repo's real ones: a route that ignored
# MODELS_DIR and read the committed models/ would fail on these strings
FAKE_HEADLINE_VERSION = "senna-ppo-feedfacecafe-C-00000064"
FAKE_ERA2024_VERSION = "senna-ppo-1187ab0c9d4e-C-00204800"


def _bake(models_dir, name, model_version, *, era=None):
    triplet = models_dir / name
    triplet.mkdir(parents=True)
    manifest = {"model_version": model_version,
                "fingerprint": model_version.split("-")[2], "stage": "C"}
    if era:
        manifest["era"] = era
    (triplet / "manifest.json").write_text(json.dumps(manifest))


@pytest.fixture
def baked_era_root(tmp_path, monkeypatch):
    """A models root after make explain ran against the era triplet: weights baked
    and the surrogate dir present, so the era model is actually servable (E-15)."""
    root = tmp_path / "models"
    _bake(root, "headline", FAKE_HEADLINE_VERSION)
    _bake(root, "era2024", FAKE_ERA2024_VERSION, era="2024")
    (root / "explain" / FAKE_ERA2024_VERSION).mkdir(parents=True)
    monkeypatch.setenv("MODELS_DIR", str(root))
    return root


@pytest.fixture
def unbaked_era_root(tmp_path, monkeypatch):
    """The same root before make explain: era weights without their surrogate. A
    worker asked to serve this model would fail the E-15 pairing check mid-job, so
    the route must degrade at POST time instead."""
    root = tmp_path / "models"
    _bake(root, "headline", FAKE_HEADLINE_VERSION)
    _bake(root, "era2024", FAKE_ERA2024_VERSION, era="2024")
    monkeypatch.setenv("MODELS_DIR", str(root))
    return root

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"),
        reason="needs Postgres; set DATABASE_URL (CI provides a service container)",
    ),
    pytest.mark.skipif(
        not os.environ.get("REDIS_URL"),
        reason="needs Redis; set REDIS_URL (CI provides a service container)",
    ),
]


def _post_pair(client, *, driver="HAM", seed=None):
    body = {"year": RACE_SEASON, "round": RACE_ROUND, "driver": driver}
    if seed is not None:
        body["seed"] = seed
    return client.post("/api/v1/counterfactuals", json=body)


def test_body_validation_requires_year_round_and_driver(client, fresh_schema, flush_redis):
    response = client.post("/api/v1/counterfactuals", json={"year": RACE_SEASON, "round": 1})
    assert response.status_code == 422


def test_an_unraced_event_is_a_404(client, fresh_schema, flush_redis):
    body = {"year": 2031, "round": 9, "driver": "VER"}
    assert client.post("/api/v1/counterfactuals", json=body).status_code == 404


def test_a_driver_not_in_the_results_is_a_404(client, fresh_schema, flush_redis):
    seed_2024_bahrain()
    body = {"year": RACE_SEASON, "round": RACE_ROUND, "driver": "ZZZ"}
    assert client.post("/api/v1/counterfactuals", json=body).status_code == 404


def test_a_driver_whose_laps_carry_no_stints_is_a_404_naming_the_gap(client, fresh_schema,
                                                                     flush_redis):
    # VER has a results row and laps, but the laps carry no stint column — there is
    # no real strategy to extract, and the detail must say which data is missing
    seed_2024_bahrain()
    response = _post_pair(client, driver="VER")
    assert response.status_code == 404, response.text
    assert "stint" in response.json()["detail"].lower()


def test_a_stint_without_compound_data_is_a_404_not_a_worker_crash(client, fresh_schema,
                                                                   flush_redis):
    # ALO's stints carry null compounds: the replay cannot pick a tyre, and that must
    # surface at POST time with the gap named, never as a runtime pair failure
    seed_2024_bahrain()
    response = _post_pair(client, driver="ALO")
    assert response.status_code == 404, response.text
    assert "compound" in response.json()["detail"].lower()


def test_the_post_answers_with_a_linked_pair_of_queued_runs(client, fresh_schema,
                                                            flush_redis, baked_era_root):
    seed_2024_bahrain()
    accepted = _post_pair(client)
    assert accepted.status_code == 202, accepted.text
    pair = accepted.json()
    agent_id, baseline_id = pair["run_id"], pair["baseline_run_id"]
    assert baseline_id != agent_id

    agent = client.get(f"/api/v1/simulations/{agent_id}").json()
    baseline = client.get(f"/api/v1/simulations/{baseline_id}").json()
    assert agent["status"] == "queued"
    assert baseline["status"] == "queued"
    # the pairing is persisted both ways so reloads and cache hits can recover it
    assert agent["config"]["baseline_run_id"] == baseline_id
    assert agent["config"]["pairing"] == "event_trace"
    # the served version is read off the baked artifact's own manifest, never a
    # literal: with the surrogate baked, the caveat is gone and the era model runs
    era_manifest = json.loads(
        (baked_era_root / "era2024" / "manifest.json").read_text())
    assert agent["config"]["era_matched_model"] == era_manifest["model_version"]
    assert agent["model_version"] == era_manifest["model_version"]
    # the real stops frozen into the config at POST time — identity rescale, because
    # the seeded race runs the same 57 laps as the sim's bahrain scenario
    assert agent["config"]["real_stops"] == HAM_REAL_STOPS
    assert baseline["config"]["agent_run_id"] == agent_id
    assert baseline["config"]["policy"] == "real_replay"
    assert baseline["model_version"] is None  # no policy network runs the replay


def test_counterfactual_route_degrades_to_pending_when_unbaked(client, fresh_schema,
                                                               flush_redis,
                                                               unbaked_era_root):
    """The graceful degrade F14 specced and never tested: a clone whose era triplet
    has no surrogate still answers, on the headline, and says so (F-24)."""
    seed_2024_bahrain()
    accepted = _post_pair(client)
    assert accepted.status_code == 202, accepted.text

    agent = client.get(f"/api/v1/simulations/{accepted.json()['run_id']}").json()
    headline = json.loads(
        (unbaked_era_root / "headline" / "manifest.json").read_text())
    assert agent["config"]["era_matched_model"] == "pending-F14"
    assert agent["model_version"] == headline["model_version"]  # the honest fallback


def test_a_seeded_post_dedupes_to_the_same_pair(client, fresh_schema, flush_redis):
    seed_2024_bahrain()
    first = _post_pair(client, seed=SEED)
    assert first.status_code == 202, first.text  # CounterfactualCreate accepts a seed
    again = _post_pair(client, seed=SEED)
    assert again.status_code < 300, again.text
    # E-15 dedupe must return the whole pair, not just the agent leg
    assert again.json()["run_id"] == first.json()["run_id"]
    assert again.json()["baseline_run_id"] == first.json()["baseline_run_id"]


@pytest.mark.slow
def test_the_pair_completes_with_identical_sc_events_and_an_honest_baseline(client, fresh_schema,
                                                                            flush_redis):
    seed_2024_bahrain()
    # this test drains real jobs, so it runs against the committed models root — the
    # served version is read off the era triplet's own manifest, never a literal
    era_version = json.loads(
        (config.REPO_ROOT / "models" / "era2024" / "manifest.json").read_text()
    )["model_version"]
    # the pairing assertion only discriminates on a race that actually threw a safety
    # car; the loop is insurance against a freak all-green seed (ws-stream precedent)
    for attempt in range(4):
        accepted = _post_pair(client, seed=SEED + attempt)
        assert accepted.status_code == 202, accepted.text
        agent_id = accepted.json()["run_id"]
        baseline_id = accepted.json()["baseline_run_id"]
        drain_queue()

        agent = client.get(f"/api/v1/simulations/{agent_id}").json()
        baseline = client.get(f"/api/v1/simulations/{baseline_id}").json()
        assert agent["status"] == "complete"
        assert baseline["status"] == "complete"
        assert agent["era"] == "2024"
        assert baseline["era"] == "2024"
        # the era-matched model recorded in the config AND echoed in the summary —
        # the summary is what screenshots quote, so the pair path cannot drop it
        assert agent["config"]["era_matched_model"] == era_version
        assert agent["summary"]["era_matched_model"] == era_version
        assert agent["model_version"] == era_version
        # E-15 honesty: the replay ran no policy network, so it must have no cards
        assert client.get(f"/api/v1/simulations/{agent_id}/decisions").json()
        assert client.get(f"/api/v1/simulations/{baseline_id}/decisions").json() == []
        assert baseline["summary"]["nominal_lap_s"] > 0  # the WS playback tempo
        assert baseline["summary"]["snapped_stops"] >= 0  # replay-honesty counter (A-07)

        agent_frames = client.get(f"/api/v1/simulations/{agent_id}/frames").json()
        baseline_frames = client.get(f"/api/v1/simulations/{baseline_id}/frames").json()
        assert agent_frames and baseline_frames
        assert all(len(frame["cars"]) == 20 for frame in agent_frames)  # physics_2024 grid
        assert all(len(frame["cars"]) == 20 for frame in baseline_frames)
        assert len(agent_frames) == len(baseline_frames)

        # the trace donor is the real-replay side: both runs must realise the very
        # same neutralisations, lap for lap (plan decision 2)
        agent_sc = [[e for e in frame["events"] if e["kind"] == "sc"]
                    for frame in agent_frames]
        baseline_sc = [[e for e in frame["events"] if e["kind"] == "sc"]
                       for frame in baseline_frames]
        assert agent_sc == baseline_sc
        if any(agent_sc):
            return
    pytest.fail("four seeds without a safety car — the pairing assertion never discriminated")


@pytest.mark.slow
def test_a_replay_failure_fails_both_runs_and_clears_the_cache(client, fresh_schema,
                                                               flush_redis, monkeypatch):
    seed_2024_bahrain()
    accepted = _post_pair(client, seed=SEED + 900)
    assert accepted.status_code == 202, accepted.text
    agent_id = accepted.json()["run_id"]
    baseline_id = accepted.json()["baseline_run_id"]

    def explode(self, obs, info, mask):
        raise RuntimeError("injected replay failure")

    # the recording episode is driven by the replay policy — killing it must fail the
    # whole pair, never leave a one-legged comparison
    monkeypatch.setattr(RealStrategyReplay, "act", explode)

    conn = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    pubsub = conn.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(events_channel(agent_id), events_channel(baseline_id))
    try:
        drain_queue()  # in-process, so the monkeypatch reaches the job

        assert client.get(f"/api/v1/simulations/{agent_id}").json()["status"] == "failed"
        assert client.get(f"/api/v1/simulations/{baseline_id}").json()["status"] == "failed"
        # E-15: a failed pair must not answer a retry for seven days
        assert not list(conn.scan_iter(match="sim:*"))

        received = {}
        deadline = time.monotonic() + 5
        while len(received) < 2 and time.monotonic() < deadline:
            message = pubsub.get_message(timeout=0.2)
            if message and message["type"] == "message":
                received[message["channel"]] = message["data"]
        # a socket waiting on either half of the pair must be told, not left hanging
        assert received == {events_channel(agent_id): "failed",
                            events_channel(baseline_id): "failed"}
    finally:
        pubsub.close()
        conn.close()
