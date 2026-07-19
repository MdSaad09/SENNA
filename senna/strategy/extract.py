"""Compile a real race's strategy into a plain pit plan (A-07, M2 groundwork).

`compile_plan` is pure — a pandas frame of one driver's laps in, a PitPlan out, no
database — so it unit-tests without any I/O and nothing pandas-shaped is ever reachable
from the env hot loop (this module is not imported by senna.strategy's package init).

Run as a script it reads the ingested Postgres store, takes the race winner's stints and
writes configs/real_strategies.yaml, which is checked in so a rollout (and CI) never needs
the database:

    python -m senna.strategy.extract --season 2024 --circuit bahrain_grand_prix
"""

import argparse

import pandas as pd

from senna.strategy.plans import PitPlan


def compile_plan(frame: pd.DataFrame, *, sim_total_laps: int, real_total_laps: int) -> PitPlan:
    """Each stint that ended in a pit becomes a stop at the next stint's out-lap, on the
    next stint's compound, with the lap rescaled to the sim distance (identity when the two
    match). The final stint never yields a stop — the race ends, not a change."""
    frame = frame.sort_values("lap_number")
    stints = [group for _, group in frame.groupby("stint")]

    stops = []
    for current, following in zip(stints[:-1], stints[1:], strict=False):
        if not current["pit_in_time_s"].notna().any():
            continue
        out_lap_real = int(following["lap_number"].min())
        compound = str(following["compound"].iloc[0])
        sim_lap = round(out_lap_real * sim_total_laps / real_total_laps)
        stops.append((sim_lap, compound))
    return PitPlan(stops=tuple(stops))


async def _winner_frame(conn, season: int, circuit: str):
    from sqlalchemy import text

    session = (await conn.execute(
        text(
            "select s.id from sessions s join events e on e.id = s.event_id "
            "where e.season = :season and e.event_name ilike :name "
            "and s.session_name in ('Race', 'R')"
        ),
        {"season": season, "name": f"%{circuit.split('_')[0]}%"},
    )).first()
    if session is None:
        raise LookupError(f"no {season} race session for {circuit}")
    session_id = session[0]

    final_lap = (await conn.execute(
        text("select max(lap_number) from laps where session_id = :s"), {"s": session_id}
    )).scalar_one()
    winner = (await conn.execute(
        text(
            "select driver_number from laps where session_id = :s and lap_number = :lap "
            "and position = 1 and source like 'real%'"
        ),
        {"s": session_id, "lap": final_lap},
    )).scalar_one()
    rows = (await conn.execute(
        text(
            "select lap_number, stint, compound, pit_in_time_s from laps "
            "where session_id = :s and driver_number = :d and source like 'real%' "
            "order by lap_number"
        ),
        {"s": session_id, "d": winner},
    )).all()
    frame = pd.DataFrame(rows, columns=["lap_number", "stint", "compound", "pit_in_time_s"])
    return frame, winner, int(final_lap)


async def _extract(season: int, circuit: str) -> dict:
    from senna import config
    from senna.data.db import database_url, engine_for

    engine = engine_for(database_url())
    async with engine.connect() as conn:
        frame, winner, real_total_laps = await _winner_frame(conn, season, circuit)
    await engine.dispose()

    sim_total_laps = int(config.get(config.load("circuits"), f"{circuit}.race_laps"))
    plan = compile_plan(frame, sim_total_laps=sim_total_laps, real_total_laps=real_total_laps)
    return {
        "winner": winner,
        "real_total_laps": real_total_laps,
        "sim_total_laps": sim_total_laps,
        "stops": [[lap, name] for lap, name in plan.stops],
    }


def main() -> None:
    import asyncio

    parser = argparse.ArgumentParser(description="extract a real race strategy into a plan")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--circuit", required=True)
    args = parser.parse_args()

    result = asyncio.run(_extract(args.season, args.circuit))
    print(f"{args.circuit} {args.season}: winner {result['winner']} -> {result['stops']}")


if __name__ == "__main__":
    main()
