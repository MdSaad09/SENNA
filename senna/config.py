"""The one loader for configs/*.yaml — the anti-black-box contract in code.

Every constant the system uses comes through here. A null in the yaml means
"not fitted yet"; reading one raises instead of guessing (configs/README.md).
"""

import hashlib
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


class NullConstantError(ValueError):
    """A constant is still null in the yaml — fit or verify it before reading it."""


def load(name: str, configs_dir: Path | None = None) -> dict:
    path = (configs_dir or REPO_ROOT / "configs") / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"no such config: {path}")
    with path.open() as handle:
        return yaml.safe_load(handle)


def fingerprint(names: list[str], configs_dir: Path | None = None) -> str:
    """A sha256 over the raw bytes of the named config files, in order — the exact configs
    an artefact was produced from. The throughput bench stamps a run with it (5.6.2), and
    the served model carries the same hash later (SimulationRun.env_config_hash)."""
    directory = configs_dir or REPO_ROOT / "configs"
    digest = hashlib.sha256()
    for name in names:
        digest.update((directory / f"{name}.yaml").read_bytes())
    return digest.hexdigest()


def get(cfg: dict, dotted_path: str):
    value = cfg
    for key in dotted_path.split("."):
        if not isinstance(value, dict) or key not in value:
            raise KeyError(f"config has no constant at '{dotted_path}'")
        value = value[key]
    if value is None:
        raise NullConstantError(
            f"'{dotted_path}' is null — fit or verify it before the phase that reads it"
        )
    return value
