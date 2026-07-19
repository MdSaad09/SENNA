"""Exact TreeSHAP on the surrogate (F-25: the tree explainer only ever sees a tree
model — the true network is crosscheck.py's business). Attributions are per class in
margin units: for any row, sum over features plus the expected value reconstructs
the booster's own logit, and the property test holds the pair to that.
"""

import numpy as np


def explain_head(booster, X, background=None):
    """SHAP values (n, features, classes) and expected values (classes,). With a
    background set the explainer is interventional — attributions are marginal
    contributions against those 1,024 documented states (5.8.2); without one it
    falls back to shap's tree-path weighting (the additivity test needs no
    background to make its claim)."""
    import shap

    if background is None:
        explainer = shap.TreeExplainer(booster)
    else:
        explainer = shap.TreeExplainer(
            booster, data=np.asarray(background), feature_perturbation="interventional"
        )
    values = np.asarray(explainer.shap_values(np.asarray(X)))
    return values, np.atleast_1d(np.asarray(explainer.expected_value))


def top_drivers(shap_row, names, k: int):
    """The card's driver list: the k features that moved this decision most, ordered
    by attribution magnitude, signs kept (positive pushed toward the call)."""
    shap_row = np.asarray(shap_row)
    order = np.argsort(-np.abs(shap_row))[:k]
    return [(names[i], float(shap_row[i])) for i in order]
