"""Elevation is decoration, never data (F-12).

Where the fastest lap carries a Z channel, we exaggerate the smoothed profile so
the ribbon reads as three-dimensional; where it does not, the ribbon lies flat
and corners get a token camber. Either way the metadata flags the choice as
stylised so the UI can say so in its legend (5.10.1 item 5).
"""

import numpy as np


def elevation_profile(
    z_m: np.ndarray | None, *, exaggeration: float, camber_deg: float, n_points: int
) -> tuple[np.ndarray, dict]:
    """Centreline height plus the stylised-provenance flags the UI surfaces."""
    flags = {"elevation": "stylised", "banking": "stylised"}
    if z_m is None:
        flags["source"] = "flat_plus_camber"
        flags["camber_deg"] = camber_deg
        return np.zeros(n_points), flags

    flags["source"] = "smoothed_z_exaggerated"
    return z_m * exaggeration, flags
