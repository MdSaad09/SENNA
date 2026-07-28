"""The seeded percentile bootstrap and the exact sign test (A-06, 5.12 M1/M2).

Every confidence interval in Chapter 7 comes out of these two functions, so what is
pinned here is the part a reader has to trust: an interval reproduces from its seed,
the point estimate is the sample's rather than the resampler's, coverage sits near the
nominal rate, and the M2 sign test needs 9 of 10 wins to clear alpha — the bar declared
before the first counterfactual roll.
"""

from statistics import fmean

import numpy as np
import pytest

from senna import config
from senna.eval.bootstrap import Interval, mean_interval, paired_sign_test
from tests.eval.conftest import SEED

ALPHA = config.load("eval")["m2"]["sign_test_alpha"]
RESAMPLES = 500  # the report runs 10,000; 500 is stable enough at these sample sizes

# a hand-written set of position deltas with no repeated value, so two different
# resampling seeds cannot land on the same percentile by grid coincidence
DELTAS = [1.24, -0.87, 2.05, 0.13, 1.66, -1.42, 3.01, 0.58, 1.19, 2.44, -0.36, 0.92]


def test_mean_interval_reproduces_from_its_seed():
    interval = mean_interval(DELTAS, level=0.95, resamples=RESAMPLES, seed=SEED)
    again = mean_interval(DELTAS, level=0.95, resamples=RESAMPLES, seed=SEED)

    assert isinstance(interval, Interval)
    assert again == interval
    assert interval.n == len(DELTAS)
    assert interval.mean == pytest.approx(fmean(DELTAS))
    assert interval.low < interval.mean < interval.high

    # the estimate belongs to the sample; only the interval around it depends on the seed
    elsewhere = mean_interval(DELTAS, level=0.95, resamples=RESAMPLES, seed=SEED + 1)
    assert elsewhere.mean == interval.mean
    assert elsewhere.n == interval.n
    assert (elsewhere.low, elsewhere.high) != (interval.low, interval.high)


@pytest.mark.property
@pytest.mark.slow
def test_bootstrap_ci_covers_at_nominal_rate():
    # 200 samples drawn from a distribution whose mean we know: a 95% interval that
    # covers far less often is too tight to claim anything, one that always covers is
    # too wide to. The band is generous because 200 trials of a percentile bootstrap
    # at n=40 genuinely scatter around 0.93-0.94.
    draws = np.random.default_rng(SEED)
    trials, true_mean = 200, 1.4

    covered = 0
    for trial in range(trials):
        sample = draws.normal(true_mean, 1.0, 40).tolist()
        interval = mean_interval(sample, level=0.95, resamples=RESAMPLES, seed=SEED + trial)
        covered += not interval.excludes(true_mean)

    assert 0.88 <= covered / trials <= 0.99


def test_interval_excludes_zero_when_the_effect_is_real():
    gains = [2.1, 1.8, 2.4, 1.9, 2.6, 2.2, 1.7, 2.0, 2.3, 2.5, 1.6, 2.8]
    interval = mean_interval(gains, level=0.95, resamples=RESAMPLES, seed=SEED)

    assert interval.low > 0.0
    assert interval.excludes(0.0)
    assert not interval.excludes(interval.mean)

    # the same spread slid onto zero: same evidence about noise, no claim left
    centred = [gain - fmean(gains) for gain in gains]
    around_zero = mean_interval(centred, level=0.95, resamples=RESAMPLES, seed=SEED)

    assert around_zero.low < 0.0 < around_zero.high
    assert not around_zero.excludes(0.0)


def test_paired_sign_test_needs_nine_of_ten():
    # the pre-registered M2 bar: at n=10 the exact two-sided test is
    # 2 * P(X >= 9 | n=10, p=0.5) = 2 * 11 / 1024
    nine_of_ten = paired_sign_test([1.4] * 9 + [-0.6])
    assert (nine_of_ten.wins, nine_of_ten.losses, nine_of_ten.ties) == (9, 1, 0)
    assert nine_of_ten.p_value == pytest.approx(22 / 1024)
    assert nine_of_ten.p_value < ALPHA

    eight_of_ten = paired_sign_test([1.4] * 8 + [-0.6, -2.0])
    assert (eight_of_ten.wins, eight_of_ten.losses, eight_of_ten.ties) == (8, 2, 0)
    assert eight_of_ten.p_value == pytest.approx(112 / 1024)
    assert eight_of_ten.p_value > ALPHA

    # a dead heat is evidence for neither side: it leaves n rather than becoming a loss
    with_ties = paired_sign_test([0.0, 0.0, 1.4, 1.4, 1.4, 1.4, 1.4, 1.4, 1.4, 1.4, 1.4, -0.6])
    assert (with_ties.wins, with_ties.losses, with_ties.ties) == (9, 1, 2)
    assert with_ties.p_value == pytest.approx(nine_of_ten.p_value)
