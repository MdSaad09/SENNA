from fastapi import APIRouter, HTTPException

from api.schemas import DegradationCurve
from senna import config
from senna.env.scenario import cliff_age_laps

router = APIRouter()


@router.get("/tyres/{slug}", response_model=list[DegradationCurve])
def degradation_curves(slug: str):
    
    fitted = config.load("physics_params")["circuits"].get(slug, {}).get("degradation")
    if not fitted:
        raise HTTPException(404, f"no degradation fits for '{slug}'")
    env_cfg = config.load("env")
    return [
        DegradationCurve(
            circuit_id=slug, era=str(era), compound=compound,
            a=params["a"], b=params["b"], low_confidence=params["low_confidence"],
            max_age_seen=params.get("max_age_seen"), n_laps=params.get("n_laps"),
            source_circuit=params.get("source_circuit"),
            cliff_age=cliff_age_laps(params.get("max_age_seen"), env_cfg),
        )
        for era, block in fitted.items()
        for compound, params in block.items()
    ]
