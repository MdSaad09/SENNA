"""The hard fidelity gate (feature spec row one): below threshold the pipeline
refuses to emit anything, and the deepen ladder is walked shallow-to-deep before
that refusal. The fit function is injected, so the walk is pinned without training
a real booster.
"""

import pytest

from senna import config
from senna.explain.surrogate import FidelityGateError, distill_or_refuse


def _ladder_and_threshold():
    cfg = config.load("explain")
    ladder = config.get(cfg, "distill.xgb_ladder")
    assert len(ladder) >= 2  # a one-rung ladder cannot deepen (5.8.2)
    return ladder, config.get(cfg, "fidelity.threshold")


def test_pipeline_refuses_cards_below_fidelity():
    ladder, threshold = _ladder_and_threshold()
    tried = []

    def underfit(rung):
        tried.append(rung)
        return object(), 0.62, 1.4  # every rung misses the bar

    with pytest.raises(FidelityGateError) as err:
        distill_or_refuse(ladder=ladder, threshold=threshold, fit_rung=underfit)

    assert tried == list(ladder)  # refusal only after the whole ladder was walked
    assert str(threshold) in str(err.value)  # the refusal names the bar it missed


def test_deepen_ladder_retries_before_refusing():
    ladder, threshold = _ladder_and_threshold()
    tried = []
    deepest_surrogate = object()

    def passes_only_at_the_deepest(rung):
        tried.append(rung)
        if len(tried) < len(ladder):
            return object(), 0.5, 2.0
        return deepest_surrogate, 0.97, 0.05

    surrogate, top1, mean_kl = distill_or_refuse(
        ladder=ladder, threshold=threshold, fit_rung=passes_only_at_the_deepest
    )

    assert tried == list(ladder)  # shallow rungs first, in config order
    assert surrogate is deepest_surrogate
    assert top1 == pytest.approx(0.97)
    assert mean_kl == pytest.approx(0.05)
