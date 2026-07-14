import pytest
from senna.config import NullConstantError, get, load


def test_load_reads_the_repo_configs_by_name():
    cfg = load("ingest")

    assert get(cfg, "openf1.first_season") == 2023  # F-11: OpenF1 starts in 2023
    assert get(cfg, "openf1.rate_limit_rps") == 3.0  # AR-15: free tier ~3 req/s
    assert get(cfg, "cleaning.telemetry_gap_split_s") == 2.0  # 5.3.4


def test_the_calibration_split_is_frozen_per_e14():
    cfg = load("data_split")

    assert get(cfg, "season") == 2026
    assert get(cfg, "calibration_rounds") == [1, 2, 3, 4, 5, 6]
    assert get(cfg, "validation_rounds_from") == 7


def test_a_null_constant_raises_the_fit_me_error(tmp_path):
    # the anti-black-box contract: null in yaml means "not fitted yet", reading it is a bug
    (tmp_path / "tyres.yaml").write_text("deg:\n  slope_s_per_lap: null\n")

    cfg = load("tyres", configs_dir=tmp_path)

    with pytest.raises(NullConstantError):
        get(cfg, "deg.slope_s_per_lap")


def test_null_constant_error_is_a_value_error():
    assert issubclass(NullConstantError, ValueError)


def test_a_missing_path_raises_key_error(tmp_path):
    (tmp_path / "tyres.yaml").write_text("deg:\n  slope_s_per_lap: 0.05\n")

    cfg = load("tyres", configs_dir=tmp_path)

    with pytest.raises(KeyError):
        get(cfg, "deg.no_such_constant")


def test_an_unknown_config_name_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load("no_such_config", configs_dir=tmp_path)
