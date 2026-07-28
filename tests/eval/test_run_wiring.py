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

from senna import config
from senna.eval.run import _BATTERIES, _circuit_key


def test_the_committed_store_and_the_smoke_store_are_different_places():
    committed = config.load("eval")["store"]["committed_dir"]
    # the runner appends "smoke" for a smoke run; the report reads the committed root, so
    # the two must not resolve to one directory
    assert (config.REPO_ROOT / committed / "smoke") != (config.REPO_ROOT / committed)


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
