"""The harvest-cap overlay (E-02, F14 decision 1).

The whole point of running the 7 MJ figure as an overlay is that the committed configs do
not move: the frozen headline's manifest records the fingerprint of configs/circuits.yaml,
and editing a value there would silently invalidate every number in the evaluation chapter.
So what is pinned here is the blast radius — the overlay rewrites the harvest cap and
nothing else, and the repository's own configs are untouched afterwards.
"""

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


def test_the_configured_value_is_the_one_written(tmp_path):
    configured = config.load("eval")["sensitivity"]["harvest_cap"]["h_max_mj"]
    dest = overlay_configs(base_dir=REPO_CONFIGS, dest=tmp_path / "overlay",
                           h_max_mj=configured)
    circuits = yaml.safe_load((dest / "circuits.yaml").read_text())

    assert {entry["h_max_mj"] for entry in circuits.values()} == {float(configured)}
