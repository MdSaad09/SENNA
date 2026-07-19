"""The frozen RL seed banks (E-14 discipline applied to RL seeds, E-06). Sizes match
the plan, every seed is globally unique, and the held-out test bank is mechanically
unreachable from F07 code — only the F14 evaluation may name itself as the consumer.
"""

import pytest

from senna import config
from senna.train.seeds import SeedBankReservedError, load_banks, load_reserved_test_bank

SUITE_SEEDS = {99, 271, 512, 704, 846}  # fits, synth, env, strategy, train

STAGE_B_SIZES = {
    "italian_grand_prix": 34,
    "spanish_grand_prix": 34,
    "british_grand_prix": 33,
    "belgian_grand_prix": 33,
    "japanese_grand_prix": 33,
    "monaco_grand_prix": 33,
}


def test_seed_banks_are_sized_and_pairwise_disjoint():
    banks = load_banks()

    assert len(banks.stage_a) == 100
    assert {circuit: len(seeds) for circuit, seeds in banks.stage_b.items()} == STAGE_B_SIZES
    assert len(banks.stage_b_overflow) == 24
    assert len(banks.stage_c_validation) == 24  # every end-to-end fitted circuit
    assert all(len(seeds) == 10 for seeds in banks.stage_c_validation.values())

    reserved = load_reserved_test_bank(consumer="F14")
    assert sum(len(seeds) for seeds in reserved.values()) == 480

    pooled = [
        *banks.stage_a,
        *(seed for seeds in banks.stage_b.values() for seed in seeds),
        *banks.stage_b_overflow,
        *(seed for seeds in banks.stage_c_validation.values() for seed in seeds),
        *(seed for seeds in reserved.values() for seed in seeds),
    ]
    assert len(pooled) == len(set(pooled))  # 1,044 seeds, none reused anywhere
    assert not set(pooled) & SUITE_SEEDS

    # the training headline seeds live in the same yaml and must not leak into any bank
    headline = set(config.load("seeds")["train"]["headline"])
    assert len(headline) == 3
    assert not set(pooled) & headline


def test_the_test_bank_loader_refuses_f07():
    with pytest.raises(SeedBankReservedError):
        load_reserved_test_bank(consumer="F07")
