"""TreeSHAP additivity (5.8.1): per class, attributions plus the expected value
reconstruct the booster's own margin. The booster here is real — a tiny
multi:softprob model on synthetic data — because the additivity claim is about
xgboost + TreeExplainer together, not about our wrapper alone.
"""

import numpy as np
import pytest
import xgboost as xgb
from hypothesis import given, settings
from hypothesis import strategies as st

from senna.explain.attributions import head_explainer
from tests.explain.conftest import SEED

N_FEATURES = 32  # the real pipeline explains the 32-dim obs; the shape contract is pinned here
N_CLASSES = 3


@pytest.fixture(scope="module")
def tiny_explainer():
    """The production path: an interventional explainer over a background set, the
    way every card is built. The tree-path fallback would make a different (and
    untested) additivity claim."""
    rng = np.random.default_rng(SEED)
    X = rng.normal(size=(400, N_FEATURES)).astype(np.float32)
    y = (X[:, 0] + X[:, 3] > 0).astype(int) + (X[:, 5] > 0.5).astype(int)
    params = {
        "objective": "multi:softprob", "num_class": N_CLASSES,
        "max_depth": 3, "eta": 0.3, "seed": SEED,
        "base_score": 0.5,  # left implicit, xgboost 3.x fits it and additivity drifts
    }
    booster = xgb.train(params, xgb.DMatrix(X, label=y), num_boost_round=8)
    return booster, head_explainer(booster, X[:64])


@pytest.mark.property
@given(row=st.lists(st.floats(-3, 3, allow_nan=False), min_size=N_FEATURES, max_size=N_FEATURES))
@settings(max_examples=25, deadline=None)
def test_treeshap_additivity(tiny_explainer, row):
    booster, explainer = tiny_explainer
    X = np.asarray([row], dtype=np.float32)

    shap_values = np.asarray(explainer.shap_values(X))
    expected_value = np.atleast_1d(np.asarray(explainer.expected_value))

    assert shap_values.shape == (1, N_FEATURES, N_CLASSES)
    assert expected_value.shape == (N_CLASSES,)
    margins = booster.predict(xgb.DMatrix(X), output_margin=True)
    assert np.allclose(shap_values[0].sum(axis=0) + expected_value, margins[0], atol=1e-4)
