"""The harvest-cap overlay (E-02, F14 decision 1).

The whole point of running the 7 MJ figure as an overlay is that the committed configs do
not move: the frozen headline's manifest records the fingerprint of configs/circuits.yaml,
and editing a value there would silently invalidate every number in the evaluation chapter.
So what is pinned here is the blast radius — the overlay rewrites the harvest cap and
nothing else, and the repository's own configs are untouched afterwards.
"""

from pathlib import Path

import pytest
import yaml

from senna import config
from senna.eval.sensitivity import overlay_configs

REPO_CONFIGS = config.REPO_ROOT / "configs"
REFINED_MJ = 7.0


def test_the_overlay_rewrites_every_harvest_cap(tmp_path):
    dest = overlay_configs(base_dir=REPO_CONFIGS, dest=tmp_path / "overlay",
                           h_max_mj=REFINED_MJ)
    circuits = yaml.safe_load((dest / "circuits.yaml").read_text())

    assert circuits, "the overlay produced an empty circuits file"
    assert {entry["h_max_mj"] for entry in circuits.values()} == {REFINED_MJ}
    # the race distances ride along untouched; rewriting one would change the episode
    # horizon and make the two arms different experiments rather than one comparison
    source = yaml.safe_load((REPO_CONFIGS / "circuits.yaml").read_text())
    assert ({name: entry["race_laps"] for name, entry in circuits.items()}
            == {name: entry["race_laps"] for name, entry in source.items()})


def test_the_overlay_touches_no_other_config(tmp_path):
    dest = overlay_configs(base_dir=REPO_CONFIGS, dest=tmp_path / "overlay",
                           h_max_mj=REFINED_MJ)

    rewritten = [path.name for path in sorted(REPO_CONFIGS.glob("*.yaml"))
                 if (dest / path.name).read_bytes() != path.read_bytes()]
    assert rewritten == ["circuits.yaml"]


def test_the_committed_configs_still_carry_the_trained_cap(tmp_path):
    """The reported numbers are measured at the cap the model trained under, so a
    sensitivity run that edited the real file would quietly rewrite the evidence."""
    before = (REPO_CONFIGS / "circuits.yaml").read_bytes()
    overlay_configs(base_dir=REPO_CONFIGS, dest=tmp_path / "overlay", h_max_mj=REFINED_MJ)

    assert (REPO_CONFIGS / "circuits.yaml").read_bytes() == before
    caps = {entry["h_max_mj"]
            for entry in yaml.safe_load(before.decode()).values()}
    assert caps == {8.5}, "the frozen headline trained at 8.5; see the circuits.yaml header"


def test_both_arms_race_the_same_seeds_under_their_own_overlay(monkeypatch):
    """The comparison is only paired if nothing but the cap differs. Selecting the arms by
    value once collapsed them into one run whenever a circuit's cap already equalled the
    refined figure, and the report printed that as a measured null result."""
    from senna.eval import sensitivity

    calls = []

    class Race:
        laps, e_dep_mj = (), 1.0

        def __init__(self):
            self.agent = type("A", (), {"final_position": 5, "pit_laps": [], "snapped": 0})()

    def fake_record(policy, *, banks, configs_dir, **kwargs):
        caps = yaml.safe_load((Path(configs_dir) / "circuits.yaml").read_text())
        calls.append({"banks": {c: tuple(s) for c, s in banks.items()},
                      "caps": {entry["h_max_mj"] for entry in caps.values()},
                      "configs_dir": Path(configs_dir)})
        return [Race()], []

    monkeypatch.setattr(sensitivity.record, "record_eval_races", fake_record)
    monkeypatch.setattr(sensitivity.record, "test_bank",
                        lambda configs_dir=None: {"bahrain_grand_prix": (1, 2, 3, 4, 5, 6)})
    monkeypatch.setattr("senna.eval.run.load_frozen_policy",
                        lambda triplet: (None, None, None, {"model_version": "stub"}))

    payload = sensitivity.run_sensitivity()

    assert len(calls) == 2
    assert calls[0]["banks"] == calls[1]["banks"], "the arms rolled different seeds"
    # each arm gets its own overlay, so neither can silently read the committed configs
    assert calls[0]["configs_dir"] != calls[1]["configs_dir"]
    assert calls[0]["caps"] == {payload["trained_h_max_mj"]}
    assert calls[1]["caps"] == {payload["refined_h_max_mj"]}


def test_a_subset_run_never_writes_where_the_report_reads(monkeypatch):
    """The same rule the suite runner follows: a partial run carries a full run's
    provenance, so writing it to the committed root would print a five-race number under
    the headline claim."""
    from senna.eval import sensitivity

    written = {}
    monkeypatch.setattr("senna.eval.store.write_metric",
                        lambda d, n, p, *, envelope: written.update(dir=Path(d), env=envelope))
    monkeypatch.setattr(sensitivity, "run_sensitivity",
                        lambda **kw: {"model_version": "stub", "n_circuits": 1,
                                      "arms": {"trained": {"n_races": 5}}})
    monkeypatch.setattr("sys.argv", ["sensitivity", "--circuits", "bahrain_grand_prix"])

    sensitivity.main()

    committed = config.REPO_ROOT / config.load("eval")["store"]["committed_dir"]
    assert written["dir"] == committed / "subset"
    assert written["dir"] != committed
    # circuits rolled, not names typed: a mistyped name must not inflate the provenance
    assert written["env"]["scope"]["circuits"] == 1
    assert written["env"]["scope"]["subset"] is True


def test_a_mixed_cap_bank_is_refused(tmp_path):
    """AR-05 permits per-event caps, and a bank spanning two of them has no single trained
    cap — labelling the arm with whichever circuit came first would be a quiet lie."""
    from senna.eval.sensitivity import trained_cap

    overlay = overlay_configs(base_dir=REPO_CONFIGS, dest=tmp_path / "mixed",
                              h_max_mj=8.5)
    circuits = yaml.safe_load((overlay / "circuits.yaml").read_text())
    first = next(iter(circuits))
    circuits[first]["h_max_mj"] = 7.0
    (overlay / "circuits.yaml").write_text(yaml.safe_dump(circuits, sort_keys=False))

    with pytest.raises(ValueError, match="harvest caps"):
        trained_cap(list(circuits)[:2], configs_dir=overlay)


def test_the_configured_value_is_the_one_written(tmp_path):
    configured = config.load("eval")["sensitivity"]["harvest_cap"]["h_max_mj"]
    dest = overlay_configs(base_dir=REPO_CONFIGS, dest=tmp_path / "overlay",
                           h_max_mj=configured)
    circuits = yaml.safe_load((dest / "circuits.yaml").read_text())

    assert {entry["h_max_mj"] for entry in circuits.values()} == {float(configured)}
