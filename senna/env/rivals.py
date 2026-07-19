"""Rival archetypes (F06, E-06). Three readable rule sets — undercutter, tyre_saver,
opportunist — drawn per race from the published bands in configs/rivals.yaml. Each rival
pits, answers a safety car and picks compounds by rules a race engineer would recognise;
the archetype only sets the thresholds those rules fire on.

Two design choices are deliberate simplifications, documented so the viva can defend them:
rivals hold BALANCED energy mode (mode variability is not an E-06 axis; per-car pace
dispersion already comes from pace_sigma_mult), and archetypes carry no mean pace offset
(that would tie strategy style to car pace and confound the paired-baseline metric M1).
The one axis E-06 mandates — the safety-car response — is a per-car Bernoulli with a
per-race drawn probability, so the field's answer to a neutralisation is never one
memorable pattern.

Everything hangs off the reset seed: draw_field consumes the env RNG in a fixed order and
pit_choices only draws on a neutralisation onset, so a SubprocVecEnv worker stays stateless
(5.5.5) and the determinism tests keep passing.
"""

from dataclasses import dataclass

import numpy as np

from senna.env.events import SC, VSC
from senna.env.scenario import compound_code

_SLICK_CODES = tuple(compound_code(c) for c in ("SOFT", "MEDIUM", "HARD"))
_INTER = compound_code("INTERMEDIATE")
_WET = compound_code("WET")
_ARCHETYPE_NAMES = ("undercutter", "tyre_saver", "opportunist")
_PARAMS = ("pit_age_frac", "sc_response_prob", "pace_sigma_mult")


@dataclass(frozen=True)
class ArchetypeBook:
    """The parsed, validated rivals.yaml — the per-archetype bands plus the field rules."""

    names: tuple
    bands: tuple
    pit_age_frac: dict          # band -> (n_arch, 2) lo/hi
    sc_response_prob: dict
    pace_sigma_mult: dict
    slick_preference: tuple     # per archetype, a tuple of compound codes
    vsc_response_scale: float
    sc_response_min_stint_frac: float
    green_stop_min_laps_left: int
    wet_crossover_jitter: float


def parse_book(cfg: dict, *, validity: dict) -> ArchetypeBook:
    """Turn the rivals.yaml dict into an ArchetypeBook, rejecting a config that would make
    the train/test split meaningless: any archetype whose train and test interval for a
    parameter overlap, or a wet-crossover jitter large enough to push the earliest
    slick-abandoner below the Intermediate band's floor (then a rival could be forced onto
    a tyre the mask forbids)."""
    archetypes = cfg["archetypes"]
    names = tuple(archetypes)
    bands = ("train", "test")

    def band_matrix(param, band):
        return np.array([archetypes[name][param][band] for name in names], dtype=float)

    tables = {param: {band: band_matrix(param, band) for band in bands} for param in _PARAMS}

    for param in _PARAMS:
        train, test = tables[param]["train"], tables[param]["test"]
        for i, name in enumerate(names):
            lo_a, hi_a = train[i]
            lo_b, hi_b = test[i]
            overlaps = not (hi_a < lo_b or hi_b < lo_a)
            if overlaps:
                raise ValueError(
                    f"rivals.yaml: {name}.{param} train {list(train[i])} and test "
                    f"{list(test[i])} overlap — the eval band must be disjoint (E-06)"
                )

    jitter = float(cfg["field"]["wet_crossover_jitter"])
    bound = validity["slick_max_wetness"] - validity["inter_band"][0]
    if jitter > bound:
        raise ValueError(
            f"rivals.yaml: wet_crossover_jitter {jitter} exceeds slick_max_wetness - "
            f"inter_band low ({bound:.3f}); the earliest wet crossover would land on an "
            "illegal tyre"
        )

    preference = tuple(
        tuple(compound_code(c) for c in archetypes[name]["slick_preference"]) for name in names
    )
    field = cfg["field"]
    return ArchetypeBook(
        names=names,
        bands=bands,
        pit_age_frac=tables["pit_age_frac"],
        sc_response_prob=tables["sc_response_prob"],
        pace_sigma_mult=tables["pace_sigma_mult"],
        slick_preference=preference,
        vsc_response_scale=float(field["vsc_response_scale"]),
        sc_response_min_stint_frac=float(field["sc_response_min_stint_frac"]),
        green_stop_min_laps_left=int(field["green_stop_min_laps_left"]),
        wet_crossover_jitter=jitter,
    )


def load_book(configs_dir=None, *, validity: dict) -> ArchetypeBook:
    from senna import config

    return parse_book(config.load("rivals", configs_dir), validity=validity)


@dataclass(frozen=True)
class RivalDraw:
    """One per race: each car's archetype and its drawn parameter values. The ego slot
    carries sentinels (archetype -1, an unreachable pit trigger, no SC response, unit
    sigma, no jitter) so the field logic never acts on the agent's car."""

    archetype: np.ndarray
    pit_age_frac: np.ndarray
    sc_response_prob: np.ndarray
    sigma_mult: np.ndarray
    wet_jitter: np.ndarray


def draw_field(book: ArchetypeBook, band: str, *, n_cars: int, ego: int, rng) -> RivalDraw:
    """Assign archetypes in balanced thirds (so every race fields all three characters, not
    a lucky near-uniform draw) and map one unit-uniform per car per parameter into that
    archetype's band. The uniforms are drawn before the band is applied, so the same seed
    gives the same field and archetype mix under either band — only the values shift, which
    keeps train/test evaluation paired."""
    if band not in book.bands:
        raise KeyError(f"no rival band '{band}' — rivals.yaml defines: {', '.join(book.bands)}")

    non_ego = np.array([c for c in range(n_cars) if c != ego], dtype=int)  # solo: empty, F07
    labels = np.resize(np.arange(len(book.names)), non_ego.size)
    archetype = np.full(n_cars, -1)
    archetype[non_ego] = rng.permutation(labels)

    def draw(param, ego_fill):
        table = getattr(book, param)[band]
        lo = np.where(archetype >= 0, table[archetype, 0], 0.0)
        hi = np.where(archetype >= 0, table[archetype, 1], 0.0)
        value = lo + rng.random(n_cars) * (hi - lo)
        value[ego] = ego_fill
        return value

    pit_age_frac = draw("pit_age_frac", np.inf)
    sc_response_prob = draw("sc_response_prob", 0.0)
    sigma_mult = draw("pace_sigma_mult", 1.0)
    wet_jitter = rng.random(n_cars) * book.wet_crossover_jitter
    wet_jitter[ego] = 0.0

    return RivalDraw(
        archetype=archetype,
        pit_age_frac=pit_age_frac,
        sc_response_prob=sc_response_prob,
        sigma_mult=sigma_mult,
        wet_jitter=wet_jitter,
    )


def pit_choices(book, draw, state, *, status_onset, red_flag, max_age_by_code,
                validity, total_laps, rng) -> np.ndarray:
    """The compound each rival boxes to this lap, or -1 to stay out (the ego slot is always
    -1 — the env overlays the agent's own choice). One priority ladder per car: a red-flag
    free change, a wet crossover, the two-compound backstop, a safety-car response, then the
    ordinary green tyre-age trigger. Every boxed compound is legal for the current wetness
    by construction, so a rival can never request a masked tyre."""
    n_cars = state.n_cars
    choice = np.full(n_cars, -1)
    wetness = float(state.wetness)
    slick_max = validity["slick_max_wetness"]
    inter_low, inter_high = validity["inter_band"]
    wet_min = validity["wet_min_wetness"]

    def legal_target(car):
        if wetness >= wet_min:
            return _WET
        if wetness > slick_max:
            return _INTER
        prefs = book.slick_preference[draw.archetype[car]]
        pick = prefs[0]
        if not state.second_compound_used[car] and pick == state.first_compound[car]:
            for candidate in prefs:
                if candidate != state.first_compound[car]:
                    return candidate
        return pick

    # a safety-car onset offers one Bernoulli response per car; drawn once, here, so the
    # RNG order stays fixed across laps that do and do not begin a neutralisation
    if status_onset in (SC, VSC):
        response_roll = rng.random(n_cars)
        scale = book.vsc_response_scale if status_onset == VSC else 1.0
    else:
        response_roll = None

    laps_left = total_laps - state.lap
    for car in range(n_cars):
        if car == state.ego or state.retired[car]:
            continue
        cur = int(state.compound[car])
        age = int(state.tyre_age[car])
        trigger_age = draw.pit_age_frac[car] * max_age_by_code[cur]

        if red_flag:
            choice[car] = legal_target(car)
            continue

        cur_slick = cur in _SLICK_CODES
        illegal_now = (
            (cur_slick and wetness > slick_max)
            or (cur == _INTER and not (inter_low <= wetness <= inter_high))
            or (cur == _WET and wetness < wet_min)
        )
        wetting = cur_slick and wetness > slick_max - draw.wet_jitter[car]
        if illegal_now or wetting:
            choice[car] = legal_target(car)
            continue

        dry = wetness <= slick_max
        if dry and not state.second_compound_used[car] and state.lap == total_laps - 1:
            choice[car] = legal_target(car)
            continue

        if response_roll is not None:
            probability = draw.sc_response_prob[car] * scale
            old_enough = age >= book.sc_response_min_stint_frac * trigger_age
            if response_roll[car] < probability and old_enough:
                choice[car] = legal_target(car)
                continue

        if age >= trigger_age and laps_left > book.green_stop_min_laps_left:
            choice[car] = legal_target(car)

    return choice
