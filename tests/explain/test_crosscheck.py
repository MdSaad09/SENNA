"""The cross-check integrity statistic (A-04): Spearman rank correlation between the
surrogate's and the gradient explainer's attribution magnitudes, with tied values
taking their average rank.
"""

import numpy as np
import pytest

from senna.explain.crosscheck import rank_correlation


def test_rank_correlation_known_value():
    # any monotone transform agrees rank-for-rank across the 32 features
    magnitudes = np.arange(32, dtype=float)
    assert rank_correlation(magnitudes, magnitudes**2) == pytest.approx(1.0)
    assert rank_correlation(magnitudes, -magnitudes) == pytest.approx(-1.0)

    # a tie takes the average rank: b ranks as (1, 2.5, 2.5, 4), and the Pearson
    # correlation of the rank vectors comes out at exactly 3/sqrt(10)
    a = np.array([1.0, 2.0, 3.0, 4.0])
    b = np.array([10.0, 20.0, 20.0, 40.0])
    assert rank_correlation(a, b) == pytest.approx(3 / np.sqrt(10))
