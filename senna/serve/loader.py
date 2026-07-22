"""The frozen serving artifacts, loaded once per worker process (F-26): the F-23
triplet (weights + VecNormalize statistics, training=False by construction) and the
F09 surrogate set TreeSHAP needs (boosters + interventional background + fidelity).
The E-15 pairing is enforced here the same way cards.py enforces it — the surrogate
manifest's version is read back off disk and must name the served checkpoint.

read_manifest is the API-process path: /health and /agents answer from the manifest
alone, so the API never imports torch.
"""

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from senna import config
from senna.explain.cards import VersionMismatchError


class UnknownModelVersionError(LookupError):
    """model_version names no baked triplet under MODELS_DIR (F-26)."""


@dataclass(frozen=True)
class ServingModel:
    model: object
    venv: object
    manifest: dict
    model_version: str
    env_config_hash: str
    boosters: dict
    background: np.ndarray
    fidelity: dict


def models_root(models_dir=None) -> Path:
    if models_dir is not None:
        return Path(models_dir)
    return Path(os.environ.get("MODELS_DIR", config.REPO_ROOT / "models"))


def resolve_version(models_dir, version: str | None) -> Path:
    """None and 5.11.2's local alias "dev-latest" mean the promoted headline; an
    explicit version must name what this image actually bakes."""
    headline = Path(models_dir) / "headline"
    if version in (None, "dev-latest"):
        return headline
    baked = json.loads((headline / "manifest.json").read_text())["model_version"]
    if version == baked:
        return headline
    raise UnknownModelVersionError(
        f"model_version '{version}' names no baked triplet — this image serves "
        f"{baked} (GET /api/v1/agents lists what is deployable)"
    )


def read_manifest(models_dir=None, version: str | None = None) -> dict:
    return json.loads((resolve_version(models_root(models_dir), version)
                       / "manifest.json").read_text())


def load_serving_model(*, models_dir=None, version: str | None = None) -> ServingModel:
    return _load(str(models_root(models_dir)), version)


@lru_cache(maxsize=4)
def _load(root: str, version: str | None) -> ServingModel:
    # heavy imports stay inside: the API imports this module for read_manifest and
    # must never pull torch into its process (plan; verified by tests/serve)
    from stable_baselines3.common.vec_env import DummyVecEnv

    from senna.env.race_env import F1RaceEnv
    from senna.explain.surrogate import load_surrogates
    from senna.train.checkpoints import load_triplet
    from senna.train.seeds import load_banks

    triplet_dir = resolve_version(Path(root), version)
    manifest = json.loads((triplet_dir / "manifest.json").read_text())
    model_version = manifest["model_version"]

    # one throwaway env for the spaces — the F09 load_headline recipe; a validation
    # circuit is guaranteed a fitted scenario
    circuit = next(iter(load_banks().stage_c_validation))
    model, venv = load_triplet(triplet_dir, DummyVecEnv([lambda: F1RaceEnv(circuit, "2026")]))

    surrogate_dir = Path(root) / "explain" / model_version
    boosters, surrogate_version = load_surrogates(surrogate_dir)
    if surrogate_version != model_version:
        raise VersionMismatchError(
            f"surrogate fitted to {surrogate_version} cannot explain "
            f"{model_version} — re-run make explain against the current triplet (E-15)"
        )
    background = np.load(surrogate_dir / "background.npz")["states"]
    fidelity = json.loads((surrogate_dir / "fidelity.json").read_text())

    return ServingModel(
        model=model, venv=venv, manifest=manifest, model_version=model_version,
        env_config_hash=manifest["fingerprint"], boosters=boosters,
        background=background, fidelity=fidelity,
    )
