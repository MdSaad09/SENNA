"""The suite runner's wiring, tested without a checkpoint.

`make suite` is what produces every number in Chapter 7, and two of its properties are
easy to break and expensive to notice. A smoke run must never write where the report
reads — its rows would carry a full run's provenance and print under a full run's claim,
which is exactly what happened once and put a four-race median in the headline table.
And M7's seeds must reproduce across processes, because a diversity number drawn from a
seed nobody can regenerate is not evidence.

The batteries themselves are pinned in their own modules against races whose answers are
known by construction. What is pinned here is the plumbing around them.
"""

import subprocess
import sys
from pathlib import Path

from senna import config
from senna.eval import run as run_module
from senna.eval.run import _BATTERIES, _circuit_key

_STUB_MANIFEST = {"model_version": "stub-C-00000000", "fingerprint": "ab" * 32}


def test_a_smoke_run_never_writes_where_the_report_reads(tmp_path, monkeypatch):
    """A smoke row carries a full run's provenance, so writing it to the committed store
    puts a four-race median in the headline table. Exercised through run_suite rather than
    asserted about paths: comparing two Path objects would pass with the branch deleted."""
    written = {}

    def fake_write(store_dir, name, payload, *, envelope):
        written[name] = Path(store_dir)
        return Path(store_dir) / f"{name}.json"

    monkeypatch.setattr(run_module.store, "write_metric", fake_write)
    monkeypatch.setattr(run_module, "load_frozen_policy",
                        lambda triplet: (None, None, None, _STUB_MANIFEST))
    monkeypatch.setattr(run_module.record, "record_eval_races",
                        lambda *a, **k: ([], []))
    monkeypatch.setattr(run_module.metrics, "legality_audit",
                        lambda races: {"illegal_actions": 0, "snapped": 0,
                                       "n_races": 0, "clean": True})

    committed = config.REPO_ROOT / config.load("eval")["store"]["committed_dir"]
    run_module.run_suite(only=["m10"], smoke=True, models_dir=tmp_path)

    assert written, "the runner wrote nothing, so this pins nothing"
    assert written["m10_legality"] != committed
    assert written["m10_legality"] == committed / "smoke"


def test_a_full_run_writes_to_the_committed_store(tmp_path, monkeypatch):
    written = {}
    monkeypatch.setattr(run_module.store, "write_metric",
                        lambda d, n, p, *, envelope: written.setdefault(n, Path(d)))
    monkeypatch.setattr(run_module, "load_frozen_policy",
                        lambda triplet: (None, None, None, _STUB_MANIFEST))
    monkeypatch.setattr(run_module.record, "record_eval_races", lambda *a, **k: ([], []))
    monkeypatch.setattr(run_module.metrics, "legality_audit",
                        lambda races: {"illegal_actions": 0, "snapped": 0,
                                       "n_races": 0, "clean": True})

    run_module.run_suite(only=["m10"], smoke=False, models_dir=tmp_path)

    assert written["m10_legality"] == (
        config.REPO_ROOT / config.load("eval")["store"]["committed_dir"]
    )


def test_circuit_key_is_stable_across_processes():
    """Python salts str.__hash__ per process, so a seed derived from it silently changes
    between runs. This is the check that would have caught that."""
    circuit = "bahrain_grand_prix"
    here = _circuit_key(circuit)

    elsewhere = subprocess.run(
        [sys.executable, "-c",
         f"from senna.eval.run import _circuit_key; print(_circuit_key({circuit!r}))"],
        capture_output=True, text=True, check=True, cwd=config.REPO_ROOT,
    )
    assert int(elsewhere.stdout.strip()) == here

    # and it separates circuits, or every circuit would draw the same races
    assert _circuit_key("monaco_grand_prix") != here


def test_m7_seed_stream_is_configured_not_inlined():
    m7 = config.load("eval")["m7"]

    assert "seed_stream" in m7, "M7's stream id belongs in configs, not in the runner"
    # and the runner must actually read it: an inlined literal would keep the key green
    import inspect
    assert 'cfg["m7"]["seed_stream"]' in inspect.getsource(run_module._diversity)
    # the rollout policy sub-stream is 91 and M11's is 173; sharing one would couple
    # draws that are supposed to be independent
    assert m7["seed_stream"] not in (91, config.load("eval")["m11"]["decision_stream"])


def test_every_battery_name_has_a_config_block_or_is_a_named_extra():
    """A battery whose targets live nowhere would render a row with no target and no
    gaming note — the one thing 5.12 says a number must never appear without."""
    cfg = config.load("eval")
    extras = {"bands"}  # the F06 band-robustness table, reported without a 5.12 target

    for battery in _BATTERIES:
        if battery in extras:
            continue
        assert battery in cfg, f"{battery} has no block in configs/eval.yaml"
        assert "gaming_note" in cfg[battery], f"{battery} has no 5.12 gaming note"
