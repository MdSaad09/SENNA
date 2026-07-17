from senna.config import get, load


def test_ribbon_constants_load_with_provenance():
    cfg = load("ribbon")

    assert get(cfg, "ribbon.resample_spacing_m") == 2.0  # stylised, spec 5.10.1 item 2
    assert get(cfg, "ribbon.width_m") == 12.0  # stylised, item 4
    assert get(cfg, "ribbon.halfwidth_clamp_fraction") == 0.9  # stylised, E-17 clamp
    assert get(cfg, "ribbon.elevation_exaggeration") == 1.5  # stylised, item 5 (F-12)
    assert get(cfg, "ribbon.savgol_window_xy") == 11  # stylised
    assert get(cfg, "ribbon.savgol_window_z") == 31  # stylised, Z smoothed harder
    assert get(cfg, "ribbon.lap_length_tolerance_pct") == 5  # sourced, item 7
    assert get(cfg, "braking.speed_drop_kmh") == 50  # sourced, item 6
    assert get(cfg, "braking.window_m") == 100  # sourced, item 6
    assert get(cfg, "xmode.full_throttle_pct") == 99  # stylised
