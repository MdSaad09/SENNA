"""Compile a real race's strategy into a plain pit plan (A-07, M2 groundwork; the
F13 counterfactual route extracts a named driver the same way).

`plan_from_rows` is the pure heart — bare tuples of one driver's laps in, a PitPlan
out, no pandas and no database — so the API route and the worker share it without
either touching a frame (nothing pandas-shaped near the serving path). `compile_plan`
keeps its pandas signature as a thin adapter for the winner script below.

Run as a script it reads the ingested Postgres store, takes the race winner's stints and
writes configs/real_strategies.yaml, which is checked in so a rollout (and CI) never needs
the database:

    python -m senna.strategy.extract --season 2024 --circuit bahrain_grand_prix
"""

import argparse

import pandas as pd

from senna.strategy.plans import PitPlan


def plan_from_rows(rows, *, sim_total_laps: int, real_total_laps: int) -> PitPlan:
    """Each stint that ended in a pit becomes a stop at the next stint's out-lap, on the
    next stint's compound, with the lap rescaled to the sim distance (identity when the
    two match). The final stint never yields a stop — the race ends, not a change. Rows
    are bare tuples in the extract query's order: (lap_number, stint, compound,
    pit_in_time_s); a null stint means FastF1 had no stint data for that lap."""
    stints: dict[int, list] = {}
    for lap_number, stint, compound, pit_in_time_s in rows:
        if stint is None:
            continue
        stints.setdefault(int(stint), []).append((int(lap_number), compound, pit_in_time_s))

    ordered = [sorted(stints[number]) for number in sorted(stints)]
    stops = []
    for current, following in zip(ordered[:-1], ordered[1:], strict=False):
        if not any(pit_in is not None for _, _, pit_in in current):
            continue
        out_lap_real, compound, _ = following[0]
        # a null compound passes through as None so the caller can 404 with a
        # message naming the gap, instead of a "None" tyre dying in the worker
        stops.append((
            round(out_lap_real * sim_total_laps / real_total_laps),
            None if compound is None else str(compound),
        ))

    # a shortened sim can rescale two out-laps onto one lap; nudging apart keeps every
    # real stop represented (dropping one would understate the strategy), and the
    # backward pass re-fits the tail under the race distance the nudge may have crossed
    laps: list[int] = []
    for lap, _ in stops:
        laps.append(max(lap, 1, laps[-1] + 1 if laps else 1))
    for i in range(len(laps) - 1, -1, -1):
        laps[i] = min(laps[i], sim_total_laps - (len(laps) - 1 - i))
    return PitPlan(stops=tuple(
        (lap, name) for lap, (_, name) in zip(laps, stops, strict=True)
    ))


def compile_plan(frame: pd.DataFrame, *, sim_total_laps: int, real_total_laps: int) -> PitPlan:
    rows = [
        (lap_number, None if pd.isna(stint) else stint, compound,
         None if pd.isna(pit_in_time_s) else pit_in_time_s)
        for lap_number, stint, compound, pit_in_time_s in frame[
            ["lap_number", "stint", "compound", "pit_in_time_s"]
        ].itertuples(index=False, name=None)
    ]
    return plan_from_rows(rows, sim_total_laps=sim_total_laps, real_total_laps=real_total_laps)


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
