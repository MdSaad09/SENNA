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


def baked_triplets(models_dir, *, configs_dir=None) -> dict:
    """The version each baked triplet carries, keyed by version string. A listed directory
    that is absent is skipped rather than fatal: a clone that never ran the era-matched
    fine-tune still has to serve the headline."""
    root = Path(models_dir)
    found = {}
    for name in config.load("serving", configs_dir)["baked_models"]:
        manifest = root / name / "manifest.json"
        if manifest.exists():
            found[json.loads(manifest.read_text())["model_version"]] = root / name
    return found


def resolve_version(models_dir, version: str | None) -> Path:
    """None and 5.11.2's local alias "dev-latest" mean the promoted headline; an
    explicit version must name what this image actually bakes."""
    headline = Path(models_dir) / "headline"
    if version in (None, "dev-latest"):
        return headline
    baked = baked_triplets(models_dir)
    if version in baked:
        return baked[version]
    raise UnknownModelVersionError(
        f"model_version '{version}' names no baked triplet — this image serves "
        f"{', '.join(sorted(baked)) or 'nothing'} "
        "(GET /api/v1/agents lists what is deployable)"
    )


def era_model_version(era: str, *, models_dir=None, configs_dir=None) -> str:
    """The version string of the triplet baked for this era, but only once it can actually
    be served. The counterfactual route stamps this into every run, so it must name a model
    the worker can load: a triplet whose SHAP surrogate has not been fitted fails the E-15
    pairing check mid-job, which would turn a graceful fallback into a broken endpoint.
    Weights without their surrogate therefore read as "not baked yet" (run make explain)."""
    root = models_root(models_dir)
    for name in config.load("serving", configs_dir)["baked_models"]:
        manifest = root / name / "manifest.json"
        if not manifest.exists():
            continue
        payload = json.loads(manifest.read_text())
        if str(payload.get("era", "2026")) != str(era):
            continue
        version = payload["model_version"]
        if not (root / "explain" / version).is_dir():
            raise UnknownModelVersionError(
                f"{version} is baked for era {era} but has no surrogate under "
                f"models/explain/{version} — run make explain against that triplet "
                "before serving it (E-15)"
            )
        return version
    raise UnknownModelVersionError(
        f"no baked triplet for era {era} — run make finetune, or the counterfactual "
        "route falls back to the frozen headline and says so (F-24)"
    )


def read_manifest(models_dir=None, version: str | None = None) -> dict:
    return json.loads((resolve_version(models_root(models_dir), version)
                       / "manifest.json").read_text())


def load_serving_model(*, models_dir=None, version: str | None = None) -> ServingModel:
    root = models_root(models_dir)
    # resolve before caching: None, "dev-latest" and the explicit baked version all
    # name one directory and must share one cache entry
    return _load(str(root), str(resolve_version(root, version)))


@lru_cache(maxsize=4)
def _load(root: str, triplet: str) -> ServingModel:
    # heavy imports stay inside: the API imports this module for read_manifest and
    # must never pull torch into its process (plan; verified by tests/serve)
    from stable_baselines3.common.vec_env import DummyVecEnv

    from senna.env.race_env import F1RaceEnv
    from senna.explain.surrogate import load_surrogates
    from senna.train.checkpoints import load_triplet
    from senna.train.seeds import load_banks

    triplet_dir = Path(triplet)
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
