import pandas as pd
from senna.data.cleaning import (
    clean_pos_data,
    drop_inaccurate,
    flag_green_laps,
    impute_laptime_for_replay,
    is_dry_race,
    missing_channels,
    split_in_out_laps,
    split_telemetry_gaps,
)
from senna.data.quality import DropCount


def test_isaccurate_false_rows_are_dropped_and_counted(make_laps):
    laps = make_laps([{}, {"IsAccurate": False}, {}, {"IsAccurate": False}, {}])

    kept, count = drop_inaccurate(laps)

    assert list(kept["LapNumber"]) == [1.0, 3.0, 5.0]
    assert kept["IsAccurate"].all()
    assert count == DropCount(rule="is_accurate", rows_in=5, rows_dropped=2, rows_flagged=0)


def test_in_and_out_laps_leave_the_pace_frame_but_stay_in_the_pit_frame(make_laps):
    laps = make_laps(
        [
            # out lap after a stop: FastF1 leaves LapTime NaT here, the classic trap
            {"PitOutTime": pd.Timedelta(seconds=95), "LapTime": pd.NaT},
            {},
            {},
            {"PitInTime": pd.Timedelta(minutes=6)},
        ]
    )

    pace, pit, count = split_in_out_laps(laps)

    assert list(pace["LapNumber"]) == [2.0, 3.0]
    # E-09: excluded from pace/degradation fits, kept for the pit-timing dataset
    assert list(pit["LapNumber"]) == [1.0, 4.0]
    assert count == DropCount(rule="in_out_laps", rows_in=4, rows_dropped=2, rows_flagged=0)


def test_a_lap_is_green_only_when_the_whole_lap_is_status_1(make_laps):
    laps = make_laps(
        [
            {"TrackStatus": "1"},
            {"TrackStatus": "4"},  # SC all lap
            {"TrackStatus": "6"},  # VSC
            {"TrackStatus": "5"},  # red
            {"TrackStatus": "12"},  # green then SC mid-lap: still not a clean lap
            {"TrackStatus": "45"},
            {"TrackStatus": "1"},
        ]
    )

    flagged, count = flag_green_laps(laps)

    assert list(flagged["is_green"]) == [True, False, False, False, False, False, True]
    # SC/VSC laps feed the event-rate fits — flag them, never drop them (5.3.4)
    assert len(flagged) == len(laps)
    assert count.rows_dropped == 0
    assert count.rows_flagged == 5


def test_nat_laptime_survives_the_fit_cleaners_unimputed(make_laps):
    laps = make_laps([{}, {"LapTime": pd.NaT}, {}])

    pace, _ = drop_inaccurate(laps)
    pace, _, _ = split_in_out_laps(pace)
    pace, _ = flag_green_laps(pace)

    # 5.3.4: never impute for fits — the NaT row passes through untouched
    assert pace["LapTime"].isna().sum() == 1
    assert "lap_time_imputed" not in pace.columns


def test_replay_imputation_fills_nat_and_flags_exactly_those_rows(make_laps):
    laps = make_laps([{}, {"LapTime": pd.NaT}, {}, {"LapTime": pd.NaT}])

    replay, count = impute_laptime_for_replay(laps)

    assert not replay["LapTime"].isna().any()
    assert list(replay["lap_time_imputed"]) == [False, True, False, True]
    assert count.rows_dropped == 0
    assert count.rows_flagged == 2
    # replay display only — the source frame the fits see keeps its NaT rows
    assert laps["LapTime"].isna().sum() == 2


def test_telemetry_gap_over_2s_splits_the_trace_without_interpolating(make_car_data):
    gap_split_s = 2.0  # cleaning.telemetry_gap_split_s (sourced 5.3.4)
    # deltas: 0.5 (keep), 2.0 (boundary: only gaps *over* 2 s split), 3.0 (split), 0.5
    car = make_car_data([0.0, 0.5, 2.5, 5.5, 6.0])

    traced, count = split_telemetry_gaps(car, gap_split_s=gap_split_s)

    assert len(traced) == len(car)  # split, never interpolate through the gap (5.3.4)
    assert list(traced["trace_id"]) == [0, 0, 0, 1, 1]
    assert count.rows_dropped == 0
    assert count.rows_flagged == 1


def test_pos_data_converts_decimetres_drops_offtrack_and_gates_outliers(make_pos_data):
    zscore_max = 4.0  # cleaning.pos_speed_zscore_max (stylised, configs/ingest.yaml)
    # 21 steady points at 5 m/s, one of them OffTrack, then a 480 m teleport
    x_dm = [10.0 * i for i in range(21)] + [5000.0]
    status = ["OnTrack"] * 22
    status[10] = "OffTrack"
    pos = make_pos_data(x_dm, status)

    cleaned, count = clean_pos_data(pos, zscore_max=zscore_max)

    # decimetres became metres; the OffTrack point and the teleport are gone (5.3.4)
    assert set(cleaned["X"]) == {float(i) for i in range(21)} - {10.0}
    assert count.rows_in == 22
    assert count.rows_dropped == 2


def test_wet_and_red_flagged_races_are_not_dry(make_weather, make_race_control):
    dry_weather = make_weather(rainfall=[False] * 5)
    wet_weather = make_weather(rainfall=[False, True, False])
    calm_control = make_race_control(flags=["GREEN", "CLEAR", "CHEQUERED"])
    red_control = make_race_control(flags=["GREEN", "RED", "GREEN"])

    assert is_dry_race(dry_weather, calm_control) is True
    # 5.3.4: excluded from dry tyre fits and analysed separately — a flag, not a drop
    assert is_dry_race(wet_weather, calm_control) is False
    assert is_dry_race(dry_weather, red_control) is False


def test_a_missing_channel_is_recorded_not_fatal(make_car_data):
    # F-14: sessions with absent channels still ingest; the gap lands in the report
    expected = ["Speed", "Throttle", "Brake", "nGear", "RPM", "DRS"]  # 5.3.2 car data
    complete = make_car_data([0.0, 0.24])

    assert missing_channels(complete, expected) == []
    assert missing_channels(complete.drop(columns=["RPM"]), expected) == ["RPM"]
    assert missing_channels(None, expected) == expected  # session had no car data at all


def test_a_truncated_stint_survives_the_cleaning_chain(make_laps):
    # F-14: a retirement truncates the stint; FastF1 half-records the final lap
    laps = make_laps(
        [
            {},
            {},
            {},
            {"LapTime": pd.NaT, "IsAccurate": False},
        ]
    )

    pace, _ = drop_inaccurate(laps)
    pace, _, _ = split_in_out_laps(pace)
    pace, _ = flag_green_laps(pace)

    assert list(pace["LapNumber"]) == [1.0, 2.0, 3.0]
    # stint metadata stays intact for the tyre fit
    assert list(pace["Stint"]) == [1.0, 1.0, 1.0]
    assert list(pace["TyreLife"]) == [1.0, 2.0, 3.0]
