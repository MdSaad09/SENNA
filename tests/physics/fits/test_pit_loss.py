import pandas as pd
import pytest
from senna.physics.fits.pit_loss import fit_pit_loss

PIT_DURATION_MAX_S = 60.0  # fits.yaml pit_duration_max_s (stylised)


def test_mean_sigma_and_count_from_clean_stops():
    stops = pd.DataFrame({"pit_duration_s": [22.0, 24.0, 26.0]})

    loss = fit_pit_loss(stops, max_duration_s=PIT_DURATION_MAX_S)

    assert loss.mean_s == pytest.approx(24.0)
    assert loss.sigma_s == pytest.approx(2.0)  # sample std, ddof=1
    assert loss.n_stops == 3
    assert loss.n_excluded == 0


def test_outliers_and_null_durations_are_excluded_and_counted():
    # a red-flag stop at 75 s and an OpenF1 row with no duration at all
    stops = pd.DataFrame({"pit_duration_s": [22.0, 24.0, 26.0, None, 75.0]})

    loss = fit_pit_loss(stops, max_duration_s=PIT_DURATION_MAX_S)

    assert loss.mean_s == pytest.approx(24.0)
    assert loss.sigma_s == pytest.approx(2.0)
    assert loss.n_stops == 3
    # exclusions feed the notebook narrative -- counted, never silent
    assert loss.n_excluded == 2
