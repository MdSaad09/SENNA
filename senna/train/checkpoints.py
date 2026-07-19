"""Checkpoint triplets (F-23): weights + VecNormalize statistics + manifest, written
atomically and hashed into their own manifest, so a served model can prove which
statistics it was frozen with. A triplet directory is never observable half-written:
the files land in a sibling .tmp dir that is swapped in whole.
"""

import hashlib
import json
import os
import shutil
from pathlib import Path


def model_version(fingerprint: str, stage: str, step: int) -> str:
    """The string F10's ModelVersion stores — config fingerprint first, so the served
    model and SimulationRun.env_config_hash agree by construction."""
    return f"senna-ppo-{fingerprint[:12]}-{stage}-{step:08d}"


def save_triplet(model, venv, dest: Path, *, manifest: dict) -> None:
    dest = Path(dest)
    tmp = dest.with_name(dest.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    model.save(tmp / "model.zip")
    venv.save(str(tmp / "vecnormalize.pkl"))
    stamped = {
        **manifest,
        # F-23: the statistics' own hash is part of the model version record
        "model_zip_sha256": _sha256(tmp / "model.zip"),
        "vecnormalize_sha256": _sha256(tmp / "vecnormalize.pkl"),
    }
    (tmp / "manifest.json").write_text(json.dumps(stamped, indent=2))

    if dest.exists():
        stale = dest.with_name(dest.name + ".stale")
        if stale.exists():
            shutil.rmtree(stale)
        os.replace(dest, stale)
        os.replace(tmp, dest)
        shutil.rmtree(stale)
    else:
        os.replace(tmp, dest)


def load_triplet(src: Path, venv):
    """Rehydrate a triplet onto a fresh vec env with the statistics frozen — the F-23
    inference contract: training=False, norm_reward untouched, same action for the
    same observation as at save time."""
    from sb3_contrib import MaskablePPO
    from stable_baselines3.common.vec_env import VecNormalize

    src = Path(src)
    loaded_venv = VecNormalize.load(str(src / "vecnormalize.pkl"), venv)
    loaded_venv.training = False
    model = MaskablePPO.load(src / "model.zip", device="cpu")
    return model, loaded_venv


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
