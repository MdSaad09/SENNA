"""Race events: the track-status transitions, the weather chain with sub-lap wetness,
and the tyre-failure cliff (spec 5.5.3, E-04, E-08). Every helper takes an explicit rng
so nothing hangs off a module global — reset() owns all the seeds (5.5.5).

A VSC is not an SC and neither is a red flag: the env keeps them as distinct states so
their different opportunities never collapse into one (E-03). Red is handled by the env
as an event (free tyre change, no termination — E-04), not sampled here.
"""

from senna import config

GREEN, VSC, SC, RED = 0, 1, 2, 3
DRY, DAMP, WET = 0, 1, 2
_WEATHER_NAMES = ("dry", "damp", "wet")


def advance_track_status(status: int, hazards: dict, rng) -> int:
    """From green, sample the next neutralisation from the per-lap hazards; once
    neutralised the env counts the state down, so this only fires green transitions."""
    if status != GREEN:
        return status
    roll = rng.random()
    cumulative = hazards["sc"]
    if roll < cumulative:
        return SC
    cumulative += hazards["vsc"]
    if roll < cumulative:
        return VSC
    cumulative += hazards["red"]
    if roll < cumulative:
        return RED
    return GREEN


def advance_weather(weather: int, wetness: float, markov: dict, n_sectors: int, rng,
                    *, target_wetness: dict | None = None) -> tuple[int, float]:
    """Step the dry/damp/wet Markov chain, then integrate wetness toward the new regime's
    target over n_sectors sub-sectors — the sub-lap resolution the crossover needs (E-08).
    The env passes cached targets; the default reads them so the helper stands alone."""
    if target_wetness is None:
        target_wetness = config.get(config.load("env"), "weather.target_wetness")

    probs = markov[_WEATHER_NAMES[weather]]
    nxt = int(rng.choice(len(_WEATHER_NAMES), p=probs))
    target = float(target_wetness[_WEATHER_NAMES[nxt]])
    for _ in range(n_sectors):
        wetness += (target - wetness) / n_sectors
    return nxt, float(min(1.0, max(0.0, wetness)))


def tyre_failure(age: int, max_age: int, cliff_margin: int, hazard_per_lap: float, rng) -> bool:
    """A set is safe up to and including its cliff (max age seen plus a margin); only past
    it does the per-lap failure hazard bite, forcing a pit rather than ending the race."""
    if age <= max_age + cliff_margin:
        return False
    return bool(rng.random() < hazard_per_lap)
