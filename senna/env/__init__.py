"""The Gymnasium environment layer (F05). The env is pure numpy plus config — nothing
pandas-shaped is importable from here, so the 5.6.2 throughput gate holds."""

from senna.env.race_env import F1RaceEnv

__all__ = ["F1RaceEnv"]
