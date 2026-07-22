from fastapi import APIRouter, HTTPException

from api.schemas import DegradationCurve
from senna import config

router = APIRouter()


@router.get("/tyres/{slug}", response_model=list[DegradationCurve])
def degradation_curves(slug: str):
    """The fitted surfaces verbatim, low_confidence included — a T5 cluster transfer
    says so itself, and the flag must survive the trip to the dashboard."""
    fitted = config.load("physics_params")["circuits"].get(slug, {}).get("degradation")
    if not fitted:
        raise HTTPException(404, f"no degradation fits for '{slug}'")
    return [
        DegradationCurve(
            circuit_id=slug, era=str(era), compound=compound,
            a=params["a"], b=params["b"], low_confidence=params["low_confidence"],
            max_age_seen=params.get("max_age_seen"), n_laps=params.get("n_laps"),
        )
        for era, block in fitted.items()
        for compound, params in block.items()
    ]
