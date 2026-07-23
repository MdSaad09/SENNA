"""The circuit library (E-13): the index is configs/circuits.yaml, coverage is
computed from what actually exists on disk and in the fits, and the ribbon URL is
relative so no server hostname can bake into a payload (F-27).
"""

import json

from fastapi import APIRouter, HTTPException

from api.schemas import CircuitDetail, CircuitSummary
from senna import config

router = APIRouter()


def _coverage(slug: str, fitted_circuits: dict) -> dict:
    ribbon = (config.REPO_ROOT / "data" / "circuits" / slug / "ribbon.glb").is_file()
    deg_fit = "degradation" in fitted_circuits.get(slug, {})
    return {"ribbon": ribbon, "deg_fit": deg_fit}


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
    coverage = _coverage(slug, config.load("physics_params")["circuits"])

    meta = {}
    meta_path = config.REPO_ROOT / "data" / "circuits" / slug / "meta.json"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text())

    return CircuitDetail(
        id=slug, race_laps=entry["race_laps"], h_max_mj=entry["h_max_mj"],
        coverage=coverage,
        gltf_url=(f"/api/v1/assets/circuits/{slug}/ribbon.glb"
                  if coverage["ribbon"] else None),
        lap_length_m=meta.get("lap_length_m"),
        corners=meta.get("corners"),
        braking_zones=meta.get("braking_zones"),
        xmode_sections=meta.get("xmode_sections"),
        flags=meta.get("flags"),
    )
