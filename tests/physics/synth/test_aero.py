import numpy as np
import pandas as pd
import pytest

from senna.physics.synth.aero import fit_corner_exponent

SEED = 271
DOWNFORCE_RATIO = 0.70  # AR-01: 2026 runs ~30 percent less downforce than 2024
EXPONENT_TRUE = 0.31
EXPONENT_PRIOR = 0.25  # spec 5.4 T2: the fourth-root prior
EXPONENT_BOUNDS = (0.1, 0.6)
MIN_CORNERS = 30
APEX_NOISE_FRAC = 0.01  # ~1 percent apex-speed scatter, well inside the 5 percent recovery bar
RECOVERY_RTOL = 0.05

_CIRCUITS = np.array(["monza", "suzuka", "spa", "miami"])


def _apex_pairs(n_corners: int, exponent: float, noise_frac: float) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    v_2024_kmh = rng.uniform(150.0, 280.0, n_corners)  # aero-dominated corners only
    scatter = 1.0 + rng.normal(0.0, noise_frac, n_corners)
    return pd.DataFrame(
        {
            "circuit": _CIRCUITS[np.arange(n_corners) % len(_CIRCUITS)],
            "v_2024_kmh": v_2024_kmh,
            "v_2026_kmh": v_2024_kmh * DOWNFORCE_RATIO**exponent * scatter,
        }
    )


def test_recovers_known_exponent():
    pairs = _apex_pairs(40, EXPONENT_TRUE, APEX_NOISE_FRAC)

    fit = fit_corner_exponent(
        pairs,
        downforce_ratio=DOWNFORCE_RATIO,
        prior=EXPONENT_PRIOR,
        bounds=EXPONENT_BOUNDS,
        min_corners=MIN_CORNERS,
    )

    assert fit.exponent == pytest.approx(EXPONENT_TRUE, rel=RECOVERY_RTOL)
    assert fit.fallback is False
    assert fit.n_corners == 40


def test_weak_sample_falls_back_to_prior_flagged():
    thin = _apex_pairs(10, EXPONENT_TRUE, noise_frac=0.0)

    fit = fit_corner_exponent(
        thin,
        downforce_ratio=DOWNFORCE_RATIO,
        prior=EXPONENT_PRIOR,
        bounds=EXPONENT_BOUNDS,
        min_corners=MIN_CORNERS,
    )

    # too few matched corners: the prior stands and the fallback is flagged, never silent
    assert fit.exponent == EXPONENT_PRIOR
    assert fit.fallback is True
    assert fit.n_corners == 10

    # a clean fit outside the plausibility gate is treated the same way: an exponent
    # of 0.9 would mean 2026 corners lost more speed than the downforce ratio allows
    implausible = _apex_pairs(40, 0.9, noise_frac=0.0)

    gated = fit_corner_exponent(
        implausible,
        downforce_ratio=DOWNFORCE_RATIO,
        prior=EXPONENT_PRIOR,
        bounds=EXPONENT_BOUNDS,
        min_corners=MIN_CORNERS,
    )

    assert gated.exponent == EXPONENT_PRIOR
    assert gated.fallback is True
