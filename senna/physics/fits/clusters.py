"""Circuit clustering for T5 degradation transfer.

Circuits the 2026 season has not visited yet borrow tyre coefficients from
the nearest cluster of circuits that it has, clustered on era-2024 behaviour
(abrasiveness and layout proxies every circuit has data for). A borrowed
coefficient is flagged low-confidence and names its donors, forever.
"""

from dataclasses import dataclass

import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class CircuitClustering:
    k: int
    assignments: dict[str, int]
    silhouettes: dict[int, float]  # the k choice, shown in the notebook


def assign_clusters(
    features: pd.DataFrame, *, k_range: tuple[int, int], seed: int
) -> CircuitClustering:
    scaled = StandardScaler().fit_transform(features.to_numpy(dtype=float))
    silhouettes: dict[int, float] = {}
    labels_by_k: dict[int, list[int]] = {}
    # silhouette needs 2 <= k <= n-1; the range is clipped, never padded
    for k in range(max(k_range[0], 2), min(k_range[1], len(features) - 1) + 1):
        labels = KMeans(n_clusters=k, random_state=seed, n_init=10).fit_predict(scaled)
        silhouettes[k] = float(silhouette_score(scaled, labels))
        labels_by_k[k] = [int(label) for label in labels]
    best_k = max(silhouettes, key=lambda k: silhouettes[k])
    return CircuitClustering(
        k=best_k,
        assignments=dict(zip(features.index, labels_by_k[best_k], strict=True)),
        silhouettes=silhouettes,
    )


def transfer_degradation(
    target_era2024_a: float,
    donor_era2024_a: float,
    donor_2026_a: float,
    donor_2026_b: float,
    source_circuit: str,
) -> dict:
    """Ratio transfer: scale the donor's 2026 amplitude by the circuits' known
    era-2024 abrasiveness ratio; the shape exponent moves unscaled."""
    return {
        "a": donor_2026_a * (target_era2024_a / donor_era2024_a),
        "b": donor_2026_b,
        "low_confidence": True,
        "source_circuit": source_circuit,
    }
