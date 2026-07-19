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

from senna.explain.attributions import explain_head
from tests.explain.conftest import SEED

N_FEATURES = 32  # the real pipeline explains the 32-dim obs; the shape contract is pinned here
N_CLASSES = 3


@pytest.fixture(scope="module")
def tiny_booster():
    rng = np.random.default_rng(SEED)
    X = rng.normal(size=(400, N_FEATURES)).astype(np.float32)
    y = (X[:, 0] + X[:, 3] > 0).astype(int) + (X[:, 5] > 0.5).astype(int)
    params = {
        "objective": "multi:softprob", "num_class": N_CLASSES,
        "max_depth": 3, "eta": 0.3, "seed": SEED,
        "base_score": 0.5,  # left implicit, xgboost 3.x fits it and additivity drifts
    }
    return xgb.train(params, xgb.DMatrix(X, label=y), num_boost_round=8)


@pytest.mark.property
@given(row=st.lists(st.floats(-3, 3, allow_nan=False), min_size=N_FEATURES, max_size=N_FEATURES))
@settings(max_examples=25, deadline=None)
def test_treeshap_additivity(tiny_booster, row):
    X = np.asarray([row], dtype=np.float32)

    shap_values, expected_value = explain_head(tiny_booster, X)

    assert shap_values.shape == (1, N_FEATURES, N_CLASSES)
    assert expected_value.shape == (N_CLASSES,)
    margins = tiny_booster.predict(xgb.DMatrix(X), output_margin=True)
    assert np.allclose(shap_values[0].sum(axis=0) + expected_value, margins[0], atol=1e-4)
