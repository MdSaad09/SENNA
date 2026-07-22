"""SimulationCreate onto F1RaceEnv construction. The typed errors are the API's
404/422 boundary; the weather map is serving.yaml's (dry -> dry, mixed and
wet_risk -> markov, decision Q2 — the requested profile is echoed verbatim on the
run instead of pretending the env distinguishes them).
"""

from senna import config
from senna.env.race_env import F1RaceEnv
from senna.env.scenario import build_scenario


class UnknownCircuitError(LookupError):
    """circuit_id has no fitted scenario — the library is data-driven (E-13)."""


class GridBoundError(ValueError):
    """grid_position exceeds the era's grid (20 cars in 2024 — plan divergence 4)."""


def build_env(req, *, configs_dir=None) -> F1RaceEnv:
    try:
        scenario = build_scenario(req.circuit_id, req.era, configs_dir=configs_dir)
    except KeyError as err:
        raise UnknownCircuitError(
            f"no fitted circuit '{req.circuit_id}' — GET /api/v1/circuits lists the library"
        ) from err
    if req.grid_position > scenario.grid_size:
        raise GridBoundError(
            f"grid_position {req.grid_position} exceeds the {req.era} grid "
            f"of {scenario.grid_size} cars"
        )
    weather = config.load("serving")["weather_profiles"][req.weather_profile]
    return F1RaceEnv(req.circuit_id, req.era, rival_band=req.rival_band,
                     weather=weather, configs_dir=configs_dir)


def circuit_slug(event_name: str) -> str:
    # the fits-layer convention (senna/physics/fits/frames.py), restated here so the
    # serving layer never imports anything pandas-shaped
    return event_name.strip().lower().replace(" ", "_")
