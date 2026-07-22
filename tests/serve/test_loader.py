"""senna.serve.loader against the real committed artifact: version resolution, the E-15
surrogate guard, and the F-23 cross-check that the served model acts exactly like the
training-eval loader on the same observation and mask.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from senna import config
from senna.explain.cards import VersionMismatchError
from senna.explain.features import FEATURE_NAMES
from senna.serve.loader import UnknownModelVersionError, load_serving_model, resolve_version
from tests.serve.conftest import CIRCUIT, SEED

MODELS_DIR = config.REPO_ROOT / "models"
HEADLINE = MODELS_DIR / "headline"

pytestmark = pytest.mark.skipif(
    not (HEADLINE / "manifest.json").is_file(),
    reason="needs the baked headline triplet (models/headline)",
)

_SURROGATE_FILES = ("pit.ubj", "mode.ubj", "background.npz",
                    "background_composition.json", "fidelity.json", "manifest.json")


def _baked_version() -> str:
    return json.loads((HEADLINE / "manifest.json").read_text())["model_version"]


def _surrogate_dir() -> Path:
    surrogate = MODELS_DIR / "explain" / _baked_version()
    if not surrogate.is_dir():
        pytest.skip("needs the baked surrogate dir (models/explain)")
    return surrogate


def test_dev_latest_and_none_both_resolve_to_the_headline_dir():
    assert Path(resolve_version(MODELS_DIR, None)) == HEADLINE
    assert Path(resolve_version(MODELS_DIR, "dev-latest")) == HEADLINE


def test_the_baked_version_resolves_and_a_stranger_refuses():
    assert Path(resolve_version(MODELS_DIR, _baked_version())) == HEADLINE
    with pytest.raises(UnknownModelVersionError):
        resolve_version(MODELS_DIR, "senna-ppo-000000000000-A-00000000")


def test_the_serving_model_loads_frozen_with_its_provenance():
    _surrogate_dir()
    serving = load_serving_model(models_dir=MODELS_DIR)
    manifest = json.loads((HEADLINE / "manifest.json").read_text())

    assert serving.venv.training is False  # F-23: statistics frozen at serve time
    assert serving.model_version == manifest["model_version"]
    assert serving.env_config_hash == manifest["fingerprint"]
    assert serving.manifest["model_version"] == manifest["model_version"]
    assert serving.boosters  # pit + mode heads
    # TreeSHAP needs the interventional background, not just the boosters
    assert np.asarray(serving.background).shape[1] == len(FEATURE_NAMES)
    assert serving.fidelity["model_version"] == manifest["model_version"]


def test_a_surrogate_fitted_to_another_checkpoint_is_refused(tmp_path):
    # E-15: never explain a ghost — the dir claims the served version, its manifest
    # says it was fitted to a different checkpoint
    surrogate_src = _surrogate_dir()
    models = tmp_path / "models"
    shutil.copytree(HEADLINE, models / "headline")
    surrogate_dst = models / "explain" / _baked_version()
    surrogate_dst.mkdir(parents=True)
    for name in _SURROGATE_FILES:
        shutil.copy(surrogate_src / name, surrogate_dst / name)
    ghost = json.loads((surrogate_dst / "manifest.json").read_text())
    ghost["model_version"] = "senna-ppo-000000000000-A-00000000"
    (surrogate_dst / "manifest.json").write_text(json.dumps(ghost))

    with pytest.raises(VersionMismatchError):
        load_serving_model(models_dir=models)


def test_read_manifest_answers_without_importing_torch():
    # /health reads the manifest in the API process, which stays torch-free (plan)
    probe = (
        "import sys\n"
        "from senna.serve.loader import read_manifest\n"
        "manifest = read_manifest()\n"
        "assert manifest['model_version']\n"
        "assert 'torch' not in sys.modules, 'read_manifest dragged torch in'\n"
    )
    subprocess.run([sys.executable, "-c", probe], check=True, cwd=config.REPO_ROOT)


def test_the_served_action_matches_the_training_eval_loader():
    from stable_baselines3.common.vec_env import DummyVecEnv

    from senna.env import F1RaceEnv
    from senna.train.checkpoints import load_triplet

    probe = F1RaceEnv(CIRCUIT, "2026")
    obs, _ = probe.reset(seed=SEED)
    mask = probe.action_masks()

    _surrogate_dir()
    serving = load_serving_model(models_dir=MODELS_DIR)
    model, venv = load_triplet(HEADLINE, DummyVecEnv([lambda: F1RaceEnv(CIRCUIT, "2026")]))

    served, _ = serving.model.predict(
        serving.venv.normalize_obs(obs), action_masks=mask, deterministic=True
    )
    trained, _ = model.predict(venv.normalize_obs(obs), action_masks=mask, deterministic=True)
    # F-23: same statistics, same head, same call — serving must equal training eval
    assert np.array_equal(served, trained)
