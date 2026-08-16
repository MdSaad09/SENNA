"""The F13 pairing mechanism, with no database in sight: run_counterfactual records
the real-replay episode once and hands that same EventTrace object to both twin rolls.
Seed pairing alone would not do — the RNG stream consumes a policy-dependent number of
variates, so two policies on one seed diverge in their events after the first
different stop (plan decision 2; the evals.py recorded-baseline convention). The
outside world — the run rows, the frozen triplet, Redis, the frame builder — is
stubbed at senna.serve.runner's own import seams; the env layer is the observation point, so
the assertion is behavioural: one recording roll donates, two twin rolls receive the
identical object.
"""

from types import SimpleNamespace

import numpy as np

import senna.serve.runner as jobs
from senna.env.twin import EventTrace
from senna.serve.runner import run_counterfactual
from tests.serve.conftest import CIRCUIT, SEED

AGENT_RUN_ID = 71
BASELINE_RUN_ID = 72


class StubEnv:
    """The slice of F1RaceEnv the job touches, over a three-lap race. Captures the
    twin it was built with and every twin its reset was handed — the seam under test."""

    def __init__(self, *, record=False, twin=None):
        self.record = record
        self.twin = twin
        self.reset_twins = []
        self.handed_out = None
        self.scenario = SimpleNamespace(t0_s=93.0, grid_size=20)
        self.n_cars = 20
        self.total_laps = 3
        self._lap = 0

    def reset(self, *, seed=None, options=None):
        options = dict(options or {})
        if "twin" in options:
            self.reset_twins.append(options["twin"])
        self._lap = 0
        return np.zeros(4, dtype=np.float32), self._info()

    def action_masks(self):
        return np.ones(10, dtype=bool)

    def step(self, action):
        self._lap += 1
        terminated = self._lap >= self.total_laps
        return np.zeros(4, dtype=np.float32), 0.0, terminated, False, self._info()

    def recorded_trace(self):
        if self.handed_out is None:
            self.handed_out = EventTrace.green(
                CIRCUIT, "2024", self.total_laps, self.n_cars,
                grid=np.arange(1, self.n_cars + 1),
            )
        return self.handed_out

    def _info(self):
        return {
            "lap": self._lap, "track_status": "green", "mask": {"reasons": {}},
            "final_position": 5, "points": 10.0, "race_time_s": 5400.0, "dnf": False,
            "pit_laps": [], "compounds": [], "derate_count": 0,
            "energy_totals": {"harvest_mj": 0.0, "deploy_mj": 0.0},
        }


class StubResult:
    def __init__(self, hits):
        self._hits = hits

    def one(self):
        return self._hits[0]

    def first(self):
        return self._hits[0] if self._hits else None

    def one_or_none(self):
        return self._hits[0] if self._hits else None

    def all(self):
        return list(self._hits)

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._hits),
                               first=lambda: self._hits[0] if self._hits else None)


class StubConn:
    """Routes SimulationRun lookups by any run id bound into the statement; every
    other statement (status updates, frame inserts) is accepted and forgotten."""

    def __init__(self, rows_by_id):
        self._rows = rows_by_id

    async def execute(self, statement, *_parameters):
        try:
            params = statement.compile().params
        except Exception:  # a bulk insert or text() we never need to route
            params = {}
        hits = [self._rows[value] for value in params.values()
                if isinstance(value, int) and value in self._rows]
        return StubResult(hits)


class _StubTransaction:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class StubEngine:
    def __init__(self, rows_by_id):
        self._rows = rows_by_id

    def begin(self):
        return _StubTransaction(StubConn(self._rows))

    def connect(self):
        return _StubTransaction(StubConn(self._rows))

    async def dispose(self):
        pass


class StubLogger:
    """DecisionLogger's surface with no torch behind it: the agent roll acts but
    records nothing, so the SHAP card path stays out of this unit."""

    def __init__(self, *args, **kwargs):
        self.records = []

    def reset(self, obs, info, *, rng=None):
        pass

    def act(self, obs, info, mask):
        return np.array([0, 1])  # stay out, balanced



def _run_rows():
    shared = {"circuit_id": CIRCUIT, "era": "2024", "grid_position": 5,
              "weather_profile": "dry", "rival_band": "test", "seed": SEED,
              "year": 2024, "round": 1, "driver": "HAM"}
    agent = SimpleNamespace(
        id=AGENT_RUN_ID, status="queued", model_version="pair-stub-model",
        env_config_hash="0" * 16, seed=SEED, circuit=CIRCUIT, purpose="counterfactual",
        config={**shared, "baseline_run_id": BASELINE_RUN_ID, "real_stops": [[2, "HARD"]],
                "pairing": "event_trace", "era_matched_model": "pending-F14"},
        summary=None, created_at=None, started_at=None, finished_at=None,
    )
    baseline = SimpleNamespace(
        id=BASELINE_RUN_ID, status="queued", model_version=None,
        env_config_hash="0" * 16, seed=SEED, circuit=CIRCUIT,
        purpose="counterfactual_baseline",
        config={**shared, "agent_run_id": AGENT_RUN_ID, "policy": "real_replay"},
        summary=None, created_at=None, started_at=None, finished_at=None,
    )
    return {AGENT_RUN_ID: agent, BASELINE_RUN_ID: baseline}


def test_the_pair_job_hands_one_recorded_trace_to_both_twin_rolls(monkeypatch):
    built = []

    def stub_build_env(req, **kwargs):
        env = StubEnv(record=bool(kwargs.get("record")), twin=kwargs.get("twin"))
        built.append(env)
        return env

    stub_serving = SimpleNamespace(
        model_version="pair-stub-model", env_config_hash="0" * 16,
        model=None, venv=SimpleNamespace(normalize_obs=lambda obs: obs),
        fidelity={"heads": {}}, boosters={}, background=None,
    )
    monkeypatch.setattr(jobs, "build_env", stub_build_env)
    monkeypatch.setattr(jobs, "load_serving_model", lambda *args, **kwargs: stub_serving)
    monkeypatch.setattr(jobs, "Sb3Policy", lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr(jobs, "DecisionLogger", StubLogger)
    monkeypatch.setattr(jobs, "build_lap_frame",
                        lambda env, info, prev: ({"lap": info["lap"], "cars": [],
                                                  "agent": {}, "events": []}, None))
    monkeypatch.setattr(jobs, "database_url", lambda: "postgresql+asyncpg://stub")
    monkeypatch.setattr(jobs, "engine_for", lambda url: StubEngine(_run_rows()))

    run_counterfactual(AGENT_RUN_ID, BASELINE_RUN_ID)

    recorders = [env for env in built if env.record]
    assert len(recorders) == 1  # exactly one recording episode donates the trace
    trace = recorders[0].handed_out
    assert trace is not None  # the job actually took recorded_trace()

    # a roll received the twin either at construction or through reset options — the
    # env supports both; what matters is that exactly two rolls replayed it and each
    # got the very same object, never a copy or a re-record
    twin_rolls = [env for env in built if env.twin is not None or env.reset_twins]
    assert len(twin_rolls) == 2
    for env in twin_rolls:
        received = ([env.twin] if env.twin is not None else []) + env.reset_twins
        assert all(handed is trace for handed in received)
