"""cliff_age_laps is the one rule the sim and the /tyres endpoint share: a compound's
failure cliff sits cliff_age_margin_laps past its fitted max_age_seen, falling back to
the tyre_age_norm_laps horizon when a transfer fit never saw a cliff. Both numbers come
from configs/env.yaml — the same file race_env.py reads — so nothing is a literal here.
"""

from senna import config
from senna.env.scenario import cliff_age_laps


def test_cliff_age_adds_the_failure_margin_to_the_fitted_support():
    env_cfg = config.load("env")
    margin = env_cfg["tyre_failure"]["cliff_age_margin_laps"]
    fallback = env_cfg["obs"]["tyre_age_norm_laps"]

    # a direct fit that saw the tyre to age 30 cliffs cliff_age_margin_laps later
    assert cliff_age_laps(30, env_cfg) == 30 + margin
    # a cluster transfer never saw a cliff — fall back to the horizon, then add the margin
    assert cliff_age_laps(None, env_cfg) == fallback + margin


def test_cliff_age_matches_the_boundary_race_env_enforces():
    # the env fails a tyre when age > max_age + cliff_margin (race_env.py:429); the
    # served cliff must be that same boundary so View 4 draws the cliff the sim runs
    env_cfg = config.load("env")
    margin = env_cfg["tyre_failure"]["cliff_age_margin_laps"]
    for max_age in (12, 24, 45):
        assert cliff_age_laps(max_age, env_cfg) == max_age + margin
