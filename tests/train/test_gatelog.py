"""curriculum_gates.json (5.7, F-21): thresholds echoed verbatim, every eval persisted
the moment it happens, and a budget_stop that can never be mistaken for a transition.
"""

import json

from senna.train.gatelog import GateLog

THRESHOLDS_A = {"plateau_window": 3, "plateau_min_improvement": 0.01, "time_tolerance": 0.015}
THRESHOLDS_B = {"finish_ahead_min": 0.55, "median_delta_min": 0.0, "n_pairs": 200}


def test_gate_log_round_trips_the_schema(tmp_path):
    path = tmp_path / "curriculum_gates.json"
    log = GateLog(
        path,
        run_id="20260719-s846-abc123def456",
        config_hash="ab" * 32,
        seeds_fingerprint="cd" * 32,
    )

    log.start_stage("A", THRESHOLDS_A)
    log.record_eval("A", step=49_152, values={"plateau_improvement": 0.4, "time_delta_frac": 0.09})
    log.record_eval("A", step=98_304, values={"plateau_improvement": 0.02, "time_delta_frac": 0.03})

    # every call persists immediately: the file is valid json before the run ends
    partial = json.loads(path.read_text())
    assert [entry["step"] for entry in partial["stages"]["A"]["evals"]] == [49_152, 98_304]

    log.record_budget_stop("A", step=1_500_000)
    log.start_stage("B", THRESHOLDS_B)
    log.record_eval("B", step=1_549_152, values={"finish_ahead_rate": 0.61})
    log.record_transition("B", step=1_549_152, reason="finish_ahead_rate and median met")

    payload = json.loads(path.read_text())
    assert payload["run_id"] == "20260719-s846-abc123def456"
    assert payload["config_hash"] == "ab" * 32
    assert payload["seeds_fingerprint"] == "cd" * 32

    stage_a = payload["stages"]["A"]
    assert stage_a["thresholds"] == THRESHOLDS_A
    assert stage_a["evals"][0]["values"]["time_delta_frac"] == 0.09
    assert stage_a["transition"] is None  # a ceiling hit is never a pass (F-21)
    assert stage_a["budget_stop"]["step"] == 1_500_000

    stage_b = payload["stages"]["B"]
    assert stage_b["thresholds"] == THRESHOLDS_B
    assert stage_b["transition"]["step"] == 1_549_152
    assert stage_b["transition"]["reason"]
    assert stage_b.get("budget_stop") is None
