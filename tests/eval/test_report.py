"""`make report` is the artifact that regenerates the Chapter 7 tables, and the plan's
acceptance criterion is that it is deterministic given the committed store (A-09). That
only means something if it is checked: a report that drifts between runs cannot be the
thing a marker reproduces from a clean clone.

So the guarantee is pinned three ways. The same store renders the same text twice, and the
same figure bytes — matplotlib stamps a creation date into a PNG unless told not to, which
would make every regenerated figure differ for no reason. Every metric's gaming note
reaches the page, because 5.12's whole design is that a target without its failure mode is
not evidence. And an empty store says so instead of rendering a confident, blank table.

Fixture stores are hand-built here: build_report takes a directory, so nothing in this file
needs a model, a database or a rollout.
"""

import json

import pytest

from senna import config
from senna.eval.report import build_report
from senna.eval.store import envelope, write_metric

HEADLINE = "senna-ppo-6b6edb78d84e-C-00835584"
ERA2024 = "senna-ppo-db031aead155-C-02211840"


def _envelope(**versions):
    return envelope(
        model_versions=versions or {"headline": HEADLINE},
        config_hash="ab" * 32,
        seeds_fingerprint="cd" * 32,
        scope={"smoke": False, "circuits": 24, "seeds_per_circuit": 20},
    )


@pytest.fixture
def store(tmp_path):
    """A store whose numbers are chosen to be unmistakable in the rendered page."""
    stamped = _envelope(headline=HEADLINE, era2024=ERA2024)
    write_metric(tmp_path, "m1_pairs", {
        "mean_delta": 2.083, "ci_low": 1.710, "ci_high": 2.475, "n": 480,
        "finish_ahead_rate": 0.627, "target": 1.0, "excludes_zero": True, "met": True,
        "per_pair": [{"circuit": "monza", "seed": 1, "agent": 4, "baseline": 6,
                      "agent_dnf": False, "baseline_dnf": False}],
    }, envelope=stamped)
    write_metric(tmp_path, "m4_energy", {
        "utilisation": 0.649, "attainable_ceiling": 0.914,
        "utilisation_of_attainable": 0.710, "derate_share": 0.080,
        "target": 0.90, "max_derate_share": 0.05, "n_green_laps": 27160, "met": False,
    }, envelope=stamped)
    write_metric(tmp_path, "m9_failures", {
        "failures_per_100": 37.29, "n_races": 480, "n_failures": 179,
        "n_races_with_failure": 179,
        "stint_laps": {"mean": 29.4, "max": 76, "n_stints": 937},
    }, envelope=stamped)
    write_metric(tmp_path, "m10_legality", {
        "illegal_actions": 0, "snapped": 0, "n_races": 480, "clean": True,
    }, envelope=stamped)
    return tmp_path


def test_report_is_byte_identical_on_a_fixture_store(store):
    first = build_report(store, figures=False)
    again = build_report(store, figures=False)

    assert first == again
    assert first  # a silently empty render would pass an equality check on its own


def test_report_is_byte_identical_across_processes(store):
    """The acceptance criterion is a marker regenerating from a clean clone, and two calls
    in one process cannot see that. Python salts str hashing per process, so any place the
    report walks a set or an unsorted dict renders differently run to run — invisible here
    and obvious to whoever diffs the committed document."""
    renders = {
        _render_in_subprocess(store, hash_seed) for hash_seed in ("0", "1", "12345")
    }

    assert len(renders) == 1, "the report depends on hash ordering somewhere"
    assert renders.pop() == build_report(store, figures=False)


def _render_in_subprocess(store, hash_seed: str) -> str:
    import os
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-c",
         "import sys; from senna.eval.report import build_report; "
         "sys.stdout.write(build_report(sys.argv[1], figures=False))", str(store)],
        capture_output=True, text=True, cwd=config.REPO_ROOT,
        env={**os.environ, "PYTHONHASHSEED": hash_seed},
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_the_table_prints_the_stored_numbers(store):
    page = build_report(store, figures=False)

    assert "2.083 places over 480 pairs" in page
    assert "[1.710, 2.475]" in page
    # M4's miss is only readable next to the ceiling its own physics allows
    assert "0.914" in page and "0.710 of attainable" in page
    assert "37.29 per 100 races" in page
    assert "| M10 regulatory legality" in page and "met |" in page


def test_every_rendered_metric_carries_its_gaming_note(store):
    page = build_report(store, figures=False)
    notes = config.load("eval")

    for block in ("m1", "m4", "m9", "m10"):
        opening = " ".join(notes[block]["gaming_note"].split())[:60]
        assert opening in page, f"{block} rendered without its 5.12 gaming note"


def test_provenance_names_every_model_that_produced_a_row(store):
    page = build_report(store, figures=False)

    # M2 runs the era-matched model and the others run the headline, so the block has to
    # union them rather than trust whichever store file happened to be read first
    assert HEADLINE in page
    assert ERA2024 in page
    assert json.loads((store / "m1_pairs.json").read_text())["envelope"]["git_commit"][:12] in page


def test_an_empty_store_says_so_rather_than_rendering_a_blank_table(tmp_path):
    page = build_report(tmp_path, figures=False)

    assert "No stored metrics found" in page
    assert "make suite" in page


def _harvest_payload():
    return {
        "arms": {"trained": {"h_max_mj": 8.5, "utilisation": 0.648,
                             "derate_share": 0.078, "mean_position": 4.81},
                 "refined": {"h_max_mj": 7.0, "utilisation": 0.627,
                             "derate_share": 0.182, "mean_position": 4.94}},
        "delta": {"utilisation": -0.021, "derate_share": 0.104,
                  "mean_position": 0.13, "failures_per_100": 0.0},
        "trained_h_max_mj": 8.5, "refined_h_max_mj": 7.0,
        "reading": "the frozen agent's robustness under a 7.0 MJ cap",
    }


def test_report_attributes_each_sections_own_hash(store):
    """The harvest study fingerprints its own overlay inputs at run time, so its
    envelope hash legitimately differs from the suite's — and a report that prints
    only the suite hash above both invites an examiner to mis-attribute it."""
    write_metric(store, "harvest_sensitivity", _harvest_payload(), envelope=envelope(
        model_versions={"headline": HEADLINE},
        config_hash="7e" * 32, seeds_fingerprint="cd" * 32,
        scope={"smoke": False, "subset": False, "circuits": 24, "seeds_per_circuit": 5},
    ))

    page = build_report(store, figures=False)

    assert ("ab" * 32)[:12] in page  # the suite envelope's hash, as before
    assert ("7e" * 32)[:12] in page  # the sensitivity run's own hash


def test_report_renders_m2_sensitivity_section(store):
    without = build_report(store, figures=False)
    assert "energy-coefficient sensitivity" not in without  # absent file, no section

    write_metric(store, "m2_sensitivity", {
        "perturbation": 0.5,
        "arms": {"up": {"mean_delta": 1.23, "n_races": 10},
                 "down": {"mean_delta": -0.45, "n_races": 10}},
    }, envelope=_envelope())
    page = build_report(store, figures=False)

    assert "energy-coefficient sensitivity" in page
    assert "50%" in page  # the perturbation, rendered as the +/-50% it is
    assert "1.23" in page and "-0.45" in page  # both arms reach the page


def test_figures_render_identically_on_a_rerun(store, tmp_path):
    """The PNGs are committed beside the document, so a creation-date stamp would make
    every regeneration a spurious diff."""
    figures = tmp_path / "figs"

    build_report(store, figures=True, figures_dir=figures)
    first = {path.name: path.read_bytes() for path in sorted(figures.glob("*.png"))}
    build_report(store, figures=True, figures_dir=figures)
    again = {path.name: path.read_bytes() for path in sorted(figures.glob("*.png"))}

    assert first, "no figures were written, so this pins nothing"
    assert first == again
