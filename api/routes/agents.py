

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
