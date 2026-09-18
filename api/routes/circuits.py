

from fastapi import APIRouter, HTTPException

from api.schemas import CircuitDetail, CircuitSummary
from senna import config

router = APIRouter()

SLICKS = ("SOFT", "MEDIUM", "HARD")


def _coverage(slug: str, fitted_circuits: dict) -> dict:
    return {"deg_fit": "degradation" in fitted_circuits.get(slug, {})}


def _compounds(slug: str, fitted_circuits: dict) -> dict:
    """Per era, which slicks have a fit and whether it is native or T5-transferred.
    This is the honest answer to "can the simulator model this tyre here" — a
    transferred curve is a borrowed one, and the write-up says so (T5)."""
    deg = (fitted_circuits.get(slug) or {}).get("degradation") or {}
    out = {}
    for era, block in deg.items():
        out[str(era)] = {
            compound: ("native" if not fit.get("source_circuit") else "transferred")
            for compound, fit in (block or {}).items()
            if compound in SLICKS
        }
    return out


@router.get("/circuits", response_model=list[CircuitSummary])
def circuit_index():
    fitted = config.load("physics_params")["circuits"]
    return [
        CircuitSummary(id=slug, race_laps=entry["race_laps"], h_max_mj=entry["h_max_mj"],
                       coverage=_coverage(slug, fitted))
        for slug, entry in config.load("circuits").items()
    ]


@router.get("/circuits/{slug}", response_model=CircuitDetail)
def circuit_detail(slug: str):
    entry = config.load("circuits").get(slug)
    if entry is None:
        raise HTTPException(404, f"no circuit '{slug}' — the library is data-driven (E-13)")
    fitted = config.load("physics_params")["circuits"]
    return CircuitDetail(
        id=slug, race_laps=entry["race_laps"], h_max_mj=entry["h_max_mj"],
        coverage=_coverage(slug, fitted), compounds=_compounds(slug, fitted),
    )
