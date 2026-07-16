import pandas as pd
import pytest

from senna.physics.fits.clusters import assign_clusters, transfer_degradation

K_RANGE = (2, 6)  # fits.yaml cluster_k_range (stylised)
SEED = 20260715  # fits.yaml cluster_seed (stylised)


def _circuit_features():
    # two well-separated groups: low-deg street-style vs high-deg power circuits
    return pd.DataFrame(
        {
            "deg_a": [0.0010, 0.0012, 0.0011, 0.0009, 0.0040, 0.0042, 0.0039, 0.0041],
            "pit_loss_s": [16.0, 16.5, 15.8, 16.2, 24.0, 24.5, 23.8, 24.2],
        },
        index=[
            "monaco",
            "singapore",
            "baku",
            "jeddah",
            "monza",
            "spa",
            "silverstone",
            "suzuka",
        ],
    )


def test_well_separated_circuits_land_in_two_clusters():
    clustering = assign_clusters(_circuit_features(), k_range=K_RANGE, seed=SEED)

    assert clustering.k == 2
    street = {clustering.assignments[slug] for slug in ["monaco", "singapore", "baku", "jeddah"]}
    power = {clustering.assignments[slug] for slug in ["monza", "spa", "silverstone", "suzuka"]}
    assert len(street) == 1
    assert len(power) == 1
    assert street != power


def test_assignments_are_deterministic_under_the_fixed_seed():
    first = assign_clusters(_circuit_features(), k_range=K_RANGE, seed=SEED)
    second = assign_clusters(_circuit_features(), k_range=K_RANGE, seed=SEED)

    # T5 transfer targets depend on these labels; a rerun of make fit must not
    # reshuffle them
    assert first.k == second.k
    assert first.assignments == second.assignments


def test_transfer_scales_by_the_era_ratio_and_flags_low_confidence():
    transferred = transfer_degradation(
        target_era2024_a=0.004,
        donor_era2024_a=0.002,
        donor_2026_a=0.003,
        donor_2026_b=1.4,
        source_circuit="monza",
    )

    assert transferred["a"] == pytest.approx(0.006)  # 0.003 * (0.004 / 0.002)
    assert transferred["b"] == pytest.approx(1.4)  # the shape exponent moves unscaled
    # T5: a borrowed coefficient must say so in the yaml, forever
    assert transferred["low_confidence"] is True
    assert transferred["source_circuit"] == "monza"
