"""Exact TreeSHAP on the surrogate (F-25: the tree explainer only ever sees a tree
model — the true network is crosscheck.py's business). Attributions are per class in
margin units: for any row, sum over features plus the expected value reconstructs
the booster's own logit, and the property test holds the pair to that.
"""

import numpy as np


def head_explainer(booster, background):
    """One interventional explainer per head, built once and reused across every
    card: attributions are marginal contributions against the 1,024 documented
    background states (5.8.2), and preparing that background is per-explainer work
    the booster does not change."""
    import shap

    return shap.TreeExplainer(booster, data=np.asarray(background),
                              feature_perturbation="interventional")


def top_drivers(shap_row, names, k: int):
    """The card's driver list: the k features that moved this decision most, ordered
    by attribution magnitude, signs kept (positive pushed toward the call)."""
    shap_row = np.asarray(shap_row)
    # stable: zero-attribution ties are common, and quicksort would order them
    # differently run to run — a card that reshuffles its drivers on a rerun
    # invites exactly the "is this thing deterministic" doubt the layer exists to kill
    order = np.argsort(-np.abs(shap_row), kind="stable")[:k]
    return [(names[i], float(shap_row[i])) for i in order]
