"""The serving model registry (F-24, E-15). From F14 the image bakes two triplets: the
frozen 2026 headline and the era-matched 2024 model the counterfactual route serves. The
loader stops special-casing one directory and reads `serving.yaml baked_models` instead.

Pinned here: both baked versions resolve to their own directory, the local aliases still
mean the headline, a listed-but-absent triplet is skipped so a clone without the era model
still serves, and an unknown version is still refused rather than quietly answered with
whatever happens to be loaded. Manifests are hand-written — resolution reads a version
string off disk and never loads a checkpoint.
"""

import json
from pathlib import Path

import pytest

from senna import config
from senna.serve.loader import UnknownModelVersionError, resolve_version

HEADLINE_VERSION = "senna-ppo-e823d1b5a2ea-C-01769472"  # the frozen 2026 headline
ERA2024_VERSION = "senna-ppo-1187ab0c9d4e-C-00204800"   # a stand-in era-matched triplet
STRANGER_VERSION = "senna-ppo-000000000000-A-00000000"


def _bake(models_dir: Path, name: str, model_version: str) -> Path:
    triplet = models_dir / name
    triplet.mkdir(parents=True)
    (triplet / "manifest.json").write_text(json.dumps({
        "model_version": model_version,
        "fingerprint": model_version.split("-")[2],
        "stage": "C",
    }))
    return triplet


def test_loader_registry_resolves_both_baked_models(tmp_path):
    assert set(config.load("serving")["baked_models"]) == {"headline", "era2024"}

    models = tmp_path / "models"
    headline = _bake(models, "headline", HEADLINE_VERSION)
    era2024 = _bake(models, "era2024", ERA2024_VERSION)

    assert Path(resolve_version(models, HEADLINE_VERSION)) == headline
    assert Path(resolve_version(models, ERA2024_VERSION)) == era2024
    assert Path(resolve_version(models, None)) == headline
    assert Path(resolve_version(models, "dev-latest")) == headline


def test_an_absent_baked_dir_is_skipped_not_fatal(tmp_path):
    # a clone that never ran make finetune has no era triplet and still has to serve
    assert "era2024" in config.load("serving")["baked_models"]

    models = tmp_path / "models"
    headline = _bake(models, "headline", HEADLINE_VERSION)
    assert not (models / "era2024").exists()

    assert Path(resolve_version(models, None)) == headline
    assert Path(resolve_version(models, HEADLINE_VERSION)) == headline


def test_an_unknown_version_still_refuses(tmp_path):
    models = tmp_path / "models"
    _bake(models, "headline", HEADLINE_VERSION)
    _bake(models, "era2024", ERA2024_VERSION)

    with pytest.raises(UnknownModelVersionError, match=STRANGER_VERSION):
        resolve_version(models, STRANGER_VERSION)
