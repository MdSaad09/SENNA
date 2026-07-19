"""Distillation mechanics (A-04): weighted hard-label row expansion reproduces the
policy's soft targets, and fidelity is scored on the surrogate exactly as cards use
it — masked to the legal actions and renormalised, never on the raw distribution.
"""

import numpy as np
import pytest

from senna.explain.surrogate import expand_soft_labels, masked_top1_and_kl


def test_row_expansion_reproduces_targets():
    X = np.array([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]], dtype=np.float32)
    probs = np.array([
        [0.7, 0.3, 0.0],      # a zero target must not become a training row
        [0.005, 0.995, 0.0],  # 0.005 sits under the floor and is dropped
        [0.2, 0.3, 0.5],
    ])

    X_out, labels, weights = expand_soft_labels(X, probs, weight_floor=0.01)

    assert len(X_out) == len(labels) == len(weights) == 6
    seen = {}
    for features, label, weight in zip(X_out, labels, weights, strict=True):
        source = next(i for i, row in enumerate(X) if np.array_equal(features, row))
        seen.setdefault(source, set()).add((int(label), float(weight)))
    assert seen[0] == {(0, 0.7), (1, 0.3)}
    assert seen[1] == {(1, 0.995)}
    assert seen[2] == {(0, 0.2), (1, 0.3), (2, 0.5)}


def test_fidelity_measured_after_masking():
    # row A: the surrogate's raw argmax (class 0) is illegal; masked + renormalised it
    # becomes [0, 0.75, 0.25] and agrees with the policy. row B: masked [0.4, 0.6, 0]
    # picks class 1 while the policy picks 0 — a genuine miss. So top-1 is exactly 0.5;
    # scoring the raw distribution instead would read 0.0.
    surrogate_probs = np.array([[0.6, 0.3, 0.1], [0.2, 0.3, 0.5]])
    policy_masked_probs = np.array([[0.0, 0.6, 0.4], [0.7, 0.3, 0.0]])
    masks = np.array([[False, True, True], [True, True, False]])

    top1, mean_kl = masked_top1_and_kl(surrogate_probs, policy_masked_probs, masks)

    assert top1 == pytest.approx(0.5)
    # KL(policy || masked surrogate) over legal actions, by hand:
    #   row A: 0.6*ln(0.6/0.75) + 0.4*ln(0.4/0.25) = 0.054115
    #   row B: 0.7*ln(0.7/0.4)  + 0.3*ln(0.3/0.6)  = 0.183787
    assert mean_kl == pytest.approx(0.118951, abs=1e-5)
