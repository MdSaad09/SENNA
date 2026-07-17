import pytest

from senna.physics.synth.residual import fit_residual_s, pool_residual_s

CALIBRATION_ROUNDS = [1, 2, 3, 4, 5, 6]  # frozen split (E-14, configs/data_split.yaml)


def test_refuses_validation_rounds(make_lap_frame):
    # Spec-mandated T8 leakage guard: a residual tuned on rounds 7+ would fold
    # the validation target into the model it is meant to validate
    held_out = make_lap_frame([{"round": 8, "session_id": "2026-08-R"} for _ in range(5)])

    with pytest.raises(ValueError, match=r"round.*8"):
        fit_residual_s(held_out, 90.0, calibration_rounds=CALIBRATION_ROUNDS)


def test_c_circuit_median_arithmetic(make_lap_frame):
    laps = make_lap_frame(
        [
            {"lap_time_s": 90.4},
            {"lap_time_s": 90.0},
            {"lap_time_s": 90.8},
            # either poison row would drag the median off 90.4 if let through (E-09)
            {"lap_time_s": 130.0, "is_green": False, "track_status": "4"},
            {"lap_time_s": 120.0, "is_accurate": False},
        ]
    )

    residual_s = fit_residual_s(laps, 89.9, calibration_rounds=CALIBRATION_ROUNDS)

    assert residual_s == pytest.approx(90.4 - 89.9)


def test_c_global_pooling():
    assert pool_residual_s({"monza": 0.2, "spa": 0.6, "suzuka": 0.4}) == pytest.approx(0.4)
    # even count: the median interpolates, it does not pick a side
    pooled = pool_residual_s({"monza": 0.2, "spa": 0.6, "suzuka": 0.4, "miami": 0.8})
    assert pooled == pytest.approx(0.5)
