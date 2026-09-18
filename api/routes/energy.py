

from fastapi import APIRouter, Request
from sqlalchemy import select

from api.routes.simulations import _serving_row
from api.schemas import EnergyLap, EnergyProfile
from senna import config
from senna.data.schema import LapFrameRow

router = APIRouter()


@router.get("/energy/{run_id}", response_model=EnergyProfile)
async def energy_profile(request: Request, run_id: int):
    row = await _serving_row(request, run_id)
    async with request.app.state.engine.connect() as conn:
        frames = (await conn.execute(
            select(LapFrameRow.frame).where(LapFrameRow.run_id == run_id)
            .order_by(LapFrameRow.lap)
        )).scalars().all()

    return EnergyProfile(
        run_id=run_id, circuit_id=row.circuit,
        h_max_mj=config.load("circuits")[row.circuit]["h_max_mj"],
        usable_soc_mj=config.load("physics_2026")["energy_store"]["usable_capacity_mj"],
        laps=[
            EnergyLap(
                lap=frame["lap"],
                harvest_mj=frame["agent"]["harvest_mj"],
                deploy_mj=frame["agent"]["deploy_mj"],
                soc_mj=frame["agent"]["soc_mj"],
                mode=frame["agent"]["mode"],
                pit=frame["agent"]["action"]["pit"],
            )
            for frame in frames
        ],
    )
