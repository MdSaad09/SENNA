import numpy as np

from senna.circuits.elevation import elevation_profile


def test_elevation_exaggerated_and_flagged_stylised():
    z_m = np.array([0.0, 1.0, 2.5, 4.0, 3.0, 1.0])

    profile, flags = elevation_profile(z_m, exaggeration=1.5, camber_deg=3.0, n_points=z_m.size)

    assert np.allclose(profile, z_m * 1.5)
    assert flags["elevation"] == "stylised"
    assert flags["banking"] == "stylised"
    assert flags["source"] == "smoothed_z_exaggerated"


def test_missing_z_falls_back_to_flat_camber_and_flagged():
    profile, flags = elevation_profile(None, exaggeration=1.5, camber_deg=3.0, n_points=100)

    assert profile.shape == (100,)
    assert np.all(profile == 0.0)
    assert flags["elevation"] == "stylised"
    assert flags["banking"] == "stylised"
    assert flags["source"] == "flat_plus_camber"
    assert flags["camber_deg"] == 3.0
