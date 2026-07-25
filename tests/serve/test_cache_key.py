"""The E-15 cache key (plan divergence 1):
sim:{model_version}:{env_hash}:{scenario_digest}:{seed}. The scenario digest exists
because the 5.9.3 key as written collides two circuits on the same seed; model_version
and env_hash come from the served manifest and pass through untouched.
"""

import re

from api.schemas import SimulationCreate
from senna import config
from senna.serve.cache import sim_cache_key, ttl_seconds

MODEL_VERSION = "senna-ppo-6b6edb78d84e-C-00835584"  # the promoted headline triplet (F08)
ENV_HASH = "6b6edb78d84e" * 5 + "6b6e"  # any 64-hex stand-in; the key never parses it

_DIGEST = re.compile(r"^[0-9a-f]{16}$")


def _request(**overrides) -> SimulationCreate:
    base = {"circuit_id": "bahrain_grand_prix", "grid_position": 5, "seed": 42}
    return SimulationCreate(**{**base, **overrides})


def _digest_of(key: str) -> str:
    return key.split(":")[3]


def test_the_key_has_the_five_agreed_segments():
    key = sim_cache_key(MODEL_VERSION, ENV_HASH, _request())
    prefix, model_version, env_hash, digest, seed = key.split(":")
    assert prefix == config.load("serving")["cache"]["key_prefix"]
    assert model_version == MODEL_VERSION  # E-15: a retrain invalidates by construction
    assert env_hash == ENV_HASH
    assert _DIGEST.match(digest)
    assert seed == "42"


def test_the_digest_is_stable_under_field_reordering():
    ordered = SimulationCreate(circuit_id="bahrain_grand_prix", era="2026", grid_position=5,
                               weather_profile="dry", rival_band="test", seed=42)
    shuffled = SimulationCreate(seed=42, rival_band="test", weather_profile="dry",
                                grid_position=5, era="2026", circuit_id="bahrain_grand_prix")
    key_a = sim_cache_key(MODEL_VERSION, ENV_HASH, ordered)
    key_b = sim_cache_key(MODEL_VERSION, ENV_HASH, shuffled)
    assert key_a == key_b


def test_seed_lives_in_its_own_segment_never_in_the_digest():
    baseline = sim_cache_key(MODEL_VERSION, ENV_HASH, _request())
    reseeded = sim_cache_key(MODEL_VERSION, ENV_HASH, _request(seed=43))
    assert _digest_of(baseline) == _digest_of(reseeded)
    assert baseline != reseeded


def test_every_scenario_field_moves_the_digest():
    baseline = _digest_of(sim_cache_key(MODEL_VERSION, ENV_HASH, _request()))
    scenario_changes = (
        {"circuit_id": "italian_grand_prix"},
        {"era": "2024"},
        {"grid_position": 6},
        {"weather_profile": "mixed"},
        {"rival_band": "train"},
    )
    for overrides in scenario_changes:
        moved = _digest_of(sim_cache_key(MODEL_VERSION, ENV_HASH, _request(**overrides)))
        assert moved != baseline, overrides


def test_purpose_moves_the_digest_so_a_pair_never_answers_a_plain_run():
    # F13: the counterfactual agent leg is twin-rolled on the replay's recorded
    # events — identical scenario and seed, different physics realisation. One
    # namespace would serve those frames to POST /simulations (and dedupe a pair
    # down to one leg), so purpose is part of the digest.
    serve = sim_cache_key(MODEL_VERSION, ENV_HASH, _request())
    pair = sim_cache_key(MODEL_VERSION, ENV_HASH, _request(), purpose="counterfactual")
    assert _digest_of(serve) != _digest_of(pair)
    assert serve.split(":")[4] == pair.split(":")[4]  # same seed segment either way


def test_the_env_hash_passes_through_untouched():
    other_hash = "ab" * 32
    key = sim_cache_key(MODEL_VERSION, other_hash, _request())
    assert key.split(":")[2] == other_hash


def test_the_ttl_is_the_yaml_seven_days():
    assert ttl_seconds() == config.load("serving")["cache"]["ttl_days"] * 86_400
