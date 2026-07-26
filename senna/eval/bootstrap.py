"""Confidence intervals for every headline number (A-06) and the exact sign test the
ten-race counterfactual claim rests on (M2).

The bootstrap is the plain percentile kind: resample the observations with replacement,
take the empirical quantiles of the resampled means. It assumes only that the races are
exchangeable, which paired evaluation buys by construction — each pair is one draw of the
same experiment. The reported point estimate is always the sample's own mean, never the
mean of the resamples, so a seed change moves the interval and never the answer.

At n=10 a bootstrap interval is descriptive at best, so M2 leads with the exact paired
sign test instead: it needs no distributional assumption and its bar (9 of 10) is
declared before the first roll.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Interval:
    mean: float
    low: float
    high: float
    n: int

    def excludes(self, value: float) -> bool:
        return value < self.low or value > self.high


@dataclass(frozen=True)
class SignTest:
    wins: int
    losses: int
    ties: int
    p_value: float


def mean_interval(values, *, level: float, resamples: int, seed: int) -> Interval:
    sample = np.asarray(list(values), dtype=float)
    if sample.size == 0:
        raise ValueError("a confidence interval over zero observations is not a claim")

    rng = np.random.default_rng(seed)
    draws = rng.integers(sample.size, size=(resamples, sample.size))
    means = sample[draws].mean(axis=1)
    tail = (1.0 - level) / 2.0
    low, high = np.quantile(means, [tail, 1.0 - tail])
    return Interval(mean=float(sample.mean()), low=float(low), high=float(high), n=int(sample.size))


def share_interval(flags, *, level: float, resamples: int, seed: int) -> Interval:
    """The same interval for a proportion — M6's hit rate and M5's precision are means
    of indicators, so they bootstrap identically once the flags are floats."""
    return mean_interval([float(bool(flag)) for flag in flags],
                         level=level, resamples=resamples, seed=seed)


def paired_sign_test(deltas) -> SignTest:
    """Exact two-sided binomial test on the signs of paired differences. Ties are dropped
    from the denominator rather than split: a dead heat is evidence for neither side, and
    counting it as half a win would manufacture precision the race did not produce."""
    from scipy.stats import binomtest

    values = [float(delta) for delta in deltas]
    wins = sum(1 for delta in values if delta > 0.0)
    losses = sum(1 for delta in values if delta < 0.0)
    ties = len(values) - wins - losses
    if wins + losses == 0:
        return SignTest(wins=wins, losses=losses, ties=ties, p_value=1.0)

    result = binomtest(wins, wins + losses, 0.5, alternative="two-sided")
    return SignTest(wins=wins, losses=losses, ties=ties, p_value=float(result.pvalue))
