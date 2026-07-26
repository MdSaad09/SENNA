"""Era threading for the F-24 / A-10 / OQ-9 fine-tune. Training is pinned to 2026 today;
F14 makes the era a per-stage config key so a Stage C fine-tune can run the 2024 world
through the same loop. Two things must hold for that to be safe.

Default drift: a stage dict with no `era` key still builds the 2026 world the frozen
headline was trained in, and the committed configs' fingerprint does not move — the era
key lives only in an overlay, never in `curriculum.yaml`. Blast radius: the fine-tune's
overlay may rewrite stage C's era, circuits and budget and nothing else, so the run stays
comparable to the headline it warm-starts from.
"""

import hashlib

import pytest
import yaml

from senna import config
from senna.env import F1RaceEnv
from senna.train import envs as envs_module
from senna.train.envs import stage_venv
from senna.train.run import CONFIG_FILES
from tests.train.conftest import SEED

REPO_CONFIGS = config.REPO_ROOT / "configs"
CIRCUIT = "bahrain_grand_prix"  # native 2024 fits, so era 2024 here is not a silent fallback
NORMALIZE = {"obs": True, "reward": False}

_MISSING = object()


def _has_key(tree, name) -> bool:
    if isinstance(tree, dict):
        return name in tree or any(_has_key(value, name) for value in tree.values())
    if isinstance(tree, list):
        return any(_has_key(value, name) for value in tree)
    return False


def _one_circuit_stage(configs_dir, **overrides):
    stage = config.load("curriculum", configs_dir)["stages"]["C"]
    return {**stage, "circuits": [CIRCUIT], **overrides}


@pytest.fixture
def built_envs(monkeypatch):
    """Every F1RaceEnv stage_venv constructed, in build order. The vec wrappers do not
    forward attribute lookups past the circuit cycler, so this is how the test reads era
    and grid size off the envs that were actually built."""
    built = []

    class RecordingEnv(F1RaceEnv):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            built.append(self)

    monkeypatch.setattr(envs_module, "F1RaceEnv", RecordingEnv)
    return built


def test_committed_config_fingerprint_is_unchanged():
    digest = hashlib.sha256()
    for name in CONFIG_FILES:
        digest.update((REPO_CONFIGS / f"{name}.yaml").read_bytes())
    assert config.fingerprint(CONFIG_FILES) == digest.hexdigest()

    curriculum_text = (REPO_CONFIGS / "curriculum.yaml").read_text()
    # the era key belongs to overlays only: adding one here would move the fingerprint the
    # frozen headline triplet carries and orphan every 2026 number in the report
    assert not _has_key(yaml.safe_load(curriculum_text), "era")
    assert "era:" not in curriculum_text


def test_stage_venv_without_an_era_key_builds_2026(built_envs, tiny_configs):
    venv = stage_venv(
        _one_circuit_stage(tiny_configs), workers=1, stage_seed=SEED, vec="dummy",
        normalize=NORMALIZE, configs_dir=tiny_configs,
    )
    venv.close()

    assert [env.era for env in built_envs] == ["2026"]
    assert built_envs[0].n_cars == 22


def test_stage_venv_honours_an_explicit_era(built_envs, tiny_configs):
    venv = stage_venv(
        _one_circuit_stage(tiny_configs, era="2024"), workers=1, stage_seed=SEED,
        vec="dummy", normalize=NORMALIZE, configs_dir=tiny_configs,
    )
    venv.close()

    assert [env.era for env in built_envs] == ["2024"]
    assert built_envs[0].n_cars == 20  # the 2024 grid, the first thing the fine-tune adapts to


def test_finetune_overlay_mutates_only_era_circuits_and_budget(tmp_path):
    # imported inside the test so the era pins above still run before senna.eval exists
    from senna.eval.finetune import overlay_configs

    eval_cfg = config.load("eval")
    dest = overlay_configs(base_dir=REPO_CONFIGS, dest=tmp_path / "overlay", cfg=eval_cfg)

    rewritten = [
        path.name for path in sorted(REPO_CONFIGS.glob("*.yaml"))
        if (dest / path.name).read_bytes() != path.read_bytes()
    ]
    assert rewritten == ["curriculum.yaml"]

    source = yaml.safe_load((REPO_CONFIGS / "curriculum.yaml").read_text())
    overlaid = yaml.safe_load((dest / "curriculum.yaml").read_text())
    outside_stages = {k: v for k, v in overlaid.items() if k != "stages"}
    assert outside_stages == {k: v for k, v in source.items() if k != "stages"}
    assert overlaid["stages"]["A"] == source["stages"]["A"]
    assert overlaid["stages"]["B"] == source["stages"]["B"]

    stage_c, source_c = overlaid["stages"]["C"], source["stages"]["C"]
    moved = {
        key for key in set(stage_c) | set(source_c)
        if stage_c.get(key, _MISSING) != source_c.get(key, _MISSING)
    }
    # the blast radius, not the write list: eval_every_steps is rewritten too but carries
    # the same Stage C cadence, so it only shows up here if someone retunes one of the two
    assert moved <= {"era", "circuits", "budget_steps", "eval_every_steps"}
    assert {"era", "circuits", "budget_steps"} <= moved

    finetune = eval_cfg["era_finetune"]
    assert stage_c["era"] == finetune["era"]
    assert stage_c["circuits"] == finetune["circuits"]
    assert stage_c["budget_steps"] == finetune["budget_steps"]
    assert stage_c["eval_every_steps"] == finetune["eval_every_steps"]
    # the 23 circuits with native 2024 fits; Canada and France would train on 2026 physics
    assert len(stage_c["circuits"]) == 23
    assert "canadian_grand_prix" not in stage_c["circuits"]
    assert "french_grand_prix" not in stage_c["circuits"]
