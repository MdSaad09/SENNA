"""The integrity statistic (A-04): GradientExplainer attributions on the true
network for a sample of decisions, rank-correlated with the surrogate's TreeSHAP.
The two explainers see different inputs (raw obs vs VecNormalize'd obs) but both
attribute in logit units over the same 32 dims, so comparing ranks is meaningful —
and 5.8.1's honesty line requires reporting how well they agree.
"""

import numpy as np
from scipy.stats import spearmanr


def rank_correlation(attr_a, attr_b) -> float:
    """Spearman rho over the 32 features, ties at their average rank."""
    return float(spearmanr(np.asarray(attr_a), np.asarray(attr_b)).statistic)


def gradient_attributions(model, normalize_obs, X_raw, background_raw, head: str):
    """|SHAP| per feature for one head's unmasked logits on the true network — the
    only place anything touches the MLP (F-25). Inputs are normalised exactly as
    the policy sees them; outputs are (n, 32, head_actions)."""
    import shap
    import torch as th

    policy = model.policy
    head_slice = {"pit": slice(0, 6), "mode": slice(6, 10)}[head]

    class _HeadLogits(th.nn.Module):
        def __init__(self):
            super().__init__()
            self.policy = policy

        def forward(self, obs):
            latent = self.policy.mlp_extractor.forward_actor(
                self.policy.pi_features_extractor(obs)
            )
            return self.policy.action_net(latent)[:, head_slice]

    background = th.as_tensor(
        np.asarray([normalize_obs(row) for row in background_raw], dtype=np.float32)
    )
    X = th.as_tensor(np.asarray([normalize_obs(row) for row in X_raw], dtype=np.float32))
    explainer = shap.GradientExplainer(_HeadLogits(), background)
    return np.asarray(explainer.shap_values(X))
