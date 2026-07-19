"""Rival archetypes on a train/test parameter split (F06, E-06). Three readable
styles are drawn per race from disjoint bands, every race fields all three, and a
safety car never collapses the field into one memorable pit pattern. Compound targets
are legal for the current wetness by construction (F-20, E-08), never leaning on the
ego's _coerce fallback.

Suite seed 704, distinct from the env suite's 512 so a cross-suite coincidence cannot
hide a bug. The mid-race states these tests probe are built here, not in conftest —
they are scaffolding for one file, not shared fixtures.
"""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from senna.env import F1RaceEnv, events
from senna.env.rivals import (
    ArchetypeBook,
    RivalDraw,
    draw_field,
    load_book,
    parse_book,
    pit_choices,
)
from senna.env.scenario import COMPOUNDS

SEED = 704
CIRCUIT = "bahrain_grand_prix"
ERA = "2026"
N_CARS = 22
EGO = 0

# the E-08 compound-validity bands, mirrored from env.yaml so the tests own their truth
VALIDITY = {"slick_max_wetness": 0.3, "inter_band": [0.25, 0.75], "wet_min_wetness": 0.7}


def _book_cfg():
    """A rivals.yaml-shaped dict with disjoint bands; tests mutate one band to break it."""

    def archetype(preference):
        return {
            "slick_preference": preference,
            "pit_age_frac": {"train": [0.50, 0.70], "test": [0.38, 0.48]},
            "sc_response_prob": {"train": [0.45, 0.65], "test": [0.66, 0.75]},
            "pace_sigma_mult": {"train": [0.95, 1.15], "test": [1.16, 1.25]},
        }

    return {
        "field": {
            "vsc_response_scale": 0.5,
            "sc_response_min_stint_frac": 0.35,
            "green_stop_min_laps_left": 4,
            "wet_crossover_jitter": 0.04,
        },
        "archetypes": {
            "undercutter": archetype(["SOFT", "MEDIUM", "HARD"]),
            "tyre_saver": archetype(["HARD", "MEDIUM", "SOFT"]),
            "opportunist": archetype(["MEDIUM", "HARD", "SOFT"]),
        },
    }


def _max_age_by_code(scenario):
    """Max tyre age per compound code; INTERMEDIATE/WET fall back to 40 laps on 2026
    circuits, where the transferred fits carry no max_age_seen (F06 plan, scenario.py)."""
    return np.array([scenario.deg_max_age.get(name, 40) for name in COMPOUNDS])


def _mid_race_state(env, *, tyre_age, wetness=0.0, track_status=events.GREEN):
    """Reset the env, then set a uniform mid-stint age and the conditions a pit-choice
    probe needs — half distance keeps clear of the two-compound backstop."""
    env.reset(seed=SEED)
    state = env._state
    state.lap = env.total_laps // 2
    state.tyre_age[:] = tyre_age
    state.wetness = wetness
    state.track_status = track_status
    return state


def _is_legal_for_wetness(code, wetness):
    slick_max = VALIDITY["slick_max_wetness"]
    inter_lo, inter_hi = VALIDITY["inter_band"]
    wet_min = VALIDITY["wet_min_wetness"]
    if code in (0, 1, 2):  # SOFT / MEDIUM / HARD
        return wetness <= slick_max
    if code == 3:  # INTERMEDIATE
        return inter_lo <= wetness <= inter_hi
    return wetness >= wet_min  # WET


def test_the_same_seed_and_band_reproduce_the_rival_draws():
    book = load_book(validity=VALIDITY)
    first = draw_field(book, "train", n_cars=N_CARS, ego=EGO, rng=np.random.default_rng(SEED))
    again = draw_field(book, "train", n_cars=N_CARS, ego=EGO, rng=np.random.default_rng(SEED))

    assert isinstance(book, ArchetypeBook)
    assert isinstance(first, RivalDraw)
    assert np.array_equal(first.archetype, again.archetype)
    assert np.array_equal(first.pit_age_frac, again.pit_age_frac)
    assert np.array_equal(first.sc_response_prob, again.sc_response_prob)
    assert np.array_equal(first.sigma_mult, again.sigma_mult)
    assert np.array_equal(first.wet_jitter, again.wet_jitter)


def test_the_test_band_changes_the_draws_but_not_the_archetype_assignment():
    book = load_book(validity=VALIDITY)
    train = draw_field(book, "train", n_cars=N_CARS, ego=EGO, rng=np.random.default_rng(SEED))
    test = draw_field(book, "test", n_cars=N_CARS, ego=EGO, rng=np.random.default_rng(SEED))

    # shared unit-uniforms fix who is which archetype, so the assignment is band-invariant
    assert np.array_equal(train.archetype, test.archetype)
    # but each parameter lands in its own disjoint interval, so the drawn values differ
    non_ego = train.archetype != -1
    assert not np.array_equal(train.pit_age_frac[non_ego], test.pit_age_frac[non_ego])
    assert not np.array_equal(train.sc_response_prob[non_ego], test.sc_response_prob[non_ego])
    assert not np.array_equal(train.sigma_mult[non_ego], test.sigma_mult[non_ego])


def test_train_and_test_bands_never_overlap_for_any_parameter():
    book = load_book(validity=VALIDITY)
    for param in (book.pit_age_frac, book.sc_response_prob, book.pace_sigma_mult):
        for archetype, name in enumerate(book.names):
            train_lo, train_hi = param["train"][archetype]
            test_lo, test_hi = param["test"][archetype]
            disjoint = train_hi < test_lo or test_hi < train_lo
            assert disjoint, f"{name}: train and test bands overlap"


def test_an_overlapping_band_is_rejected_at_parse():
    cfg = _book_cfg()
    # train [0.45, 0.65] now straddles test [0.60, 0.75]: the two intervals intersect
    cfg["archetypes"]["undercutter"]["sc_response_prob"]["test"] = [0.60, 0.75]

    with pytest.raises(ValueError):
        parse_book(cfg, validity=VALIDITY)


def test_an_unknown_band_is_refused_and_names_the_known_bands():
    book = load_book(validity=VALIDITY)
    with pytest.raises(KeyError) as drawn:
        draw_field(book, "validation", n_cars=N_CARS, ego=EGO, rng=np.random.default_rng(SEED))
    message = str(drawn.value)
    assert "train" in message and "test" in message

    with pytest.raises(KeyError):
        F1RaceEnv(CIRCUIT, ERA, rival_band="validation")


def test_every_race_fields_all_three_archetypes():
    book = load_book(validity=VALIDITY)
    for seed in (SEED, SEED + 1, SEED + 7, SEED + 100):
        draw = draw_field(book, "train", n_cars=N_CARS, ego=EGO, rng=np.random.default_rng(seed))
        non_ego = draw.archetype[draw.archetype != -1]
        counts = np.bincount(non_ego, minlength=len(book.names))
        assert list(counts) == [7, 7, 7]


@pytest.mark.property
@pytest.mark.slow
@given(seed=st.integers(min_value=0, max_value=2**31 - 1))
@settings(max_examples=150, deadline=None)
def test_drawn_parameters_stay_inside_their_band(seed):
    book = load_book(validity=VALIDITY)
    band = "train"
    draw = draw_field(book, band, n_cars=N_CARS, ego=EGO, rng=np.random.default_rng(seed))

    for car in np.flatnonzero(draw.archetype != -1):
        arch = int(draw.archetype[car])
        pit_lo, pit_hi = book.pit_age_frac[band][arch]
        sc_lo, sc_hi = book.sc_response_prob[band][arch]
        sig_lo, sig_hi = book.pace_sigma_mult[band][arch]
        assert pit_lo <= draw.pit_age_frac[car] <= pit_hi
        assert sc_lo <= draw.sc_response_prob[car] <= sc_hi
        assert sig_lo <= draw.sigma_mult[car] <= sig_hi


def test_sc_responses_vary_across_archetype_draws():
    # E-06 degeneracy: with the field uniformly aged past the SC-eligibility floor but
    # short of any green pit trigger, boxing under a safety car is purely each car's
    # per-race Bernoulli response — it must not read as one memorable field-wide pattern.
    book = load_book(validity=VALIDITY)
    env = F1RaceEnv(CIRCUIT, ERA)
    state = _mid_race_state(env, tyre_age=15, track_status=events.SC)
    max_age = _max_age_by_code(env.scenario)

    boxed = []
    for seed in range(SEED, SEED + 12):
        draw = draw_field(
            book, "train", n_cars=env.n_cars, ego=EGO, rng=np.random.default_rng(seed)
        )
        choice = pit_choices(
            book, draw, state,
            status_onset=events.SC, red_flag=False,
            max_age_by_code=max_age, validity=VALIDITY,
            total_laps=env.total_laps, rng=np.random.default_rng(seed + 5000),
        )
        boxed.append(choice[draw.archetype != -1] >= 0)

    responses = np.array(boxed)
    assert not all(np.array_equal(responses[0], row) for row in responses[1:])
    assert responses.any()  # someone answers the safety car
    assert not responses.all()  # and someone stays out


@pytest.mark.property
@pytest.mark.slow
@given(
    seed=st.integers(min_value=0, max_value=2**31 - 1),
    wetness=st.floats(min_value=0.0, max_value=1.0),
    onset=st.sampled_from([events.GREEN, events.VSC, events.SC]),
)
@settings(max_examples=80, deadline=None)
def test_rivals_never_fit_an_illegal_compound_for_the_wetness(seed, wetness, onset):
    book = load_book(validity=VALIDITY)
    env = F1RaceEnv(CIRCUIT, ERA)
    state = _mid_race_state(env, tyre_age=25, wetness=wetness, track_status=onset)
    max_age = _max_age_by_code(env.scenario)
    draw = draw_field(book, "train", n_cars=env.n_cars, ego=EGO, rng=np.random.default_rng(seed))

    choice = pit_choices(
        book, draw, state,
        status_onset=onset, red_flag=False,
        max_age_by_code=max_age, validity=VALIDITY,
        total_laps=env.total_laps, rng=np.random.default_rng(seed + 1),
    )

    for code in choice[choice >= 0]:
        assert _is_legal_for_wetness(int(code), wetness)


def test_every_rival_runs_two_compounds_in_a_dry_race():
    env = F1RaceEnv(CIRCUIT, ERA)
    env.reset(seed=SEED)
    terminated = False
    while not terminated:
        _, _, terminated, _, _ = env.step(np.array([0, 1]))

    state = env._state
    non_ego = np.arange(state.n_cars) != state.ego
    finishers = non_ego & ~state.retired
    assert finishers.any()
    # F-20 made explicit: every rival that reaches the flag has run two distinct compounds
    assert state.second_compound_used[finishers].all()


def test_rival_lap_noise_scales_with_the_drawn_sigma():
    # each rival's pace_sigma_mult scales its per-lap pace noise; the ego keeps unit sigma
    # so the agent's own noise model is untouched. This dispersion is the pace half of an
    # archetype's identity and what M1's paired comparison leans on (E-06).
    env = F1RaceEnv(CIRCUIT, ERA)
    env.reset(seed=SEED)
    n = env.n_cars
    sigma_mult = np.ones(n)
    sigma_mult[1] = 0.2  # a metronome
    sigma_mult[2] = 3.0  # a scrappy, high-variance driver
    env._rivals = RivalDraw(
        archetype=np.full(n, -1),
        pit_age_frac=np.full(n, np.inf),
        sc_response_prob=np.zeros(n),
        sigma_mult=sigma_mult,
        wet_jitter=np.zeros(n),
    )

    noise = np.array([env._lap_noise() for _ in range(4000)])
    spread = noise.std(axis=0)
    assert spread[2] > spread[1]  # a higher multiplier is a wider spread
    assert spread[env._state.ego] == pytest.approx(env.scenario.s_ref_s, rel=0.1)


def test_a_red_flag_gives_every_rival_a_legal_archetype_chosen_change():
    # E-04: the free change is archetype- and wetness-aware, not one forced HARD monoculture
    book = load_book(validity=VALIDITY)
    env = F1RaceEnv(CIRCUIT, ERA)
    state = _mid_race_state(env, tyre_age=10, wetness=0.0)
    max_age = _max_age_by_code(env.scenario)
    draw = draw_field(book, "train", n_cars=env.n_cars, ego=EGO, rng=np.random.default_rng(SEED))

    choice = pit_choices(
        book, draw, state,
        status_onset=events.GREEN, red_flag=True,
        max_age_by_code=max_age, validity=VALIDITY,
        total_laps=env.total_laps, rng=np.random.default_rng(SEED),
    )

    changed = choice[draw.archetype != -1]
    assert (changed >= 0).all()  # everyone takes the free set
    for code in changed:
        assert _is_legal_for_wetness(int(code), 0.0)
    assert len(set(changed.tolist())) > 1  # different styles pick different compounds
