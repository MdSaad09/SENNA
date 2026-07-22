"""GET /agents: the registry answers from the baked artifact's own files — manifest,
promotion, fidelity — never from a database row that could drift from what the image
actually serves (F-23, F-26).
"""

import json

from fastapi import APIRouter

from api.schemas import ModelVersion
from senna.serve.loader import models_root, read_manifest

router = APIRouter()


@router.get("/agents", response_model=list[ModelVersion])
def model_registry():
    manifest = read_manifest()
    root = models_root()

    promotion = {}
    promotion_path = root / "headline" / "promotion.json"
    if promotion_path.is_file():
        promotion = json.loads(promotion_path.read_text())

    fidelity = None
    fidelity_path = root / "explain" / manifest["model_version"] / "fidelity.json"
    if fidelity_path.is_file():
        badge = json.loads(fidelity_path.read_text())
        fidelity = {head: fit["top1"] for head, fit in badge["heads"].items()}

    return [ModelVersion(
        version=manifest["model_version"],
        eval_points=promotion.get("mean_points"),
        fidelity=fidelity,
        config_hash=manifest["fingerprint"],
        promoted_at=promotion.get("promoted_at"),
    )]
