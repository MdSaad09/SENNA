"""The checkpoint triplet (F-23): weights, VecNormalize statistics and manifest saved
together, each artifact hashed into the manifest, and reloaded onto a fresh venv with
training frozen. SB3 loads at module scope because every test here needs it.
"""

import json
import re

import numpy as np
from sb3_contrib import MaskablePPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from senna.env import F1RaceEnv
from senna.train.checkpoints import load_triplet, model_version, save_triplet
from tests.train.conftest import CIRCUIT, SEED

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


def _make_env():
    return F1RaceEnv(CIRCUIT, "2026")


def _fresh_venv():
    return DummyVecEnv([_make_env, _make_env])


def test_checkpoint_roundtrip(tmp_path):
    venv = VecNormalize(_fresh_venv(), norm_obs=True, norm_reward=False)
    model = MaskablePPO(
        "MlpPolicy", venv, n_steps=8, batch_size=16, n_epochs=1,
        policy_kwargs={"net_arch": {"pi": [16], "vf": [16]}}, seed=SEED, device="cpu",
    )
    model.learn(total_timesteps=16)  # one tiny rollout, so obs_rms moves off its init

    dest = tmp_path / "stageA" / "last"
    save_triplet(model, venv, dest, manifest={"stage": "A", "global_step": 16})

    manifest = json.loads((dest / "manifest.json").read_text())
    assert manifest["stage"] == "A"
    # F-23: the stats' own hash is part of the model version record
    assert _SHA256_HEX.match(manifest["model_zip_sha256"])
    assert _SHA256_HEX.match(manifest["vecnormalize_sha256"])

    loaded_model, loaded_venv = load_triplet(dest, _fresh_venv())
    assert loaded_venv.training is False  # evaluation must never keep moving the stats
    assert np.array_equal(loaded_venv.obs_rms.mean, venv.obs_rms.mean)
    assert np.array_equal(loaded_venv.obs_rms.var, venv.obs_rms.var)

    probe = _make_env()
    obs, _ = probe.reset(seed=SEED)
    mask = probe.action_masks()
    action_before, _ = model.predict(
        venv.normalize_obs(obs), action_masks=mask, deterministic=True
    )
    action_after, _ = loaded_model.predict(
        loaded_venv.normalize_obs(obs), action_masks=mask, deterministic=True
    )
    assert np.array_equal(action_before, action_after)


def test_model_version_embeds_the_fingerprint():
    version = model_version("0123456789abcdef0123456789abcdef", "B", 1_234_567)
    assert version == "senna-ppo-0123456789ab-B-01234567"
