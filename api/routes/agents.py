"""GET /agents: the registry answers from the baked artifacts' own files — manifest,
promotion, fidelity — never from a database row that could drift from what the image
actually serves (F-23, F-26). One entry per baked triplet (F-24: the era-matched
model is deployable too), each badge read from that model's own surrogate.
"""

import json

from fastapi import APIRouter

from api.schemas import ModelVersion
from senna.serve.loader import baked_triplets, models_root

router = APIRouter()


@router.get("/agents", response_model=list[ModelVersion])
def model_registry():
    root = models_root()

    entries = []
    for version, triplet in baked_triplets(root).items():
        manifest = json.loads((triplet / "manifest.json").read_text())

        promotion = {}
        promotion_path = triplet / "promotion.json"
        if promotion_path.is_file():
            promotion = json.loads(promotion_path.read_text())

        fidelity = None
        fidelity_path = root / "explain" / version / "fidelity.json"
        if fidelity_path.is_file():
            badge = json.loads(fidelity_path.read_text())
            fidelity = {head: fit["top1"] for head, fit in badge["heads"].items()}

        entries.append(ModelVersion(
            version=version,
            eval_points=promotion.get("mean_points"),
            fidelity=fidelity,
            config_hash=manifest["fingerprint"],
            promoted_at=promotion.get("promoted_at"),
        ))
    return entries
