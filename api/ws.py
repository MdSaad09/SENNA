"""WS /ws/simulations/{run_id} (5.9.3): a playback clock over stored frames, never a
re-simulation. The worker finished the whole race before any client connects in
practice; a socket that arrives early polls the run row at ws.status_poll_s until the
store is complete (E-16 — the store, not the socket, is the source of truth).

The inter-frame sleep is app.state.playback_sleep so tests replay a 57-lap race in
milliseconds; 1x means one wall second per simulated second, so the delay divides the
circuit's fitted nominal lap time by the client's speed.
"""

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from api.deps import serving_config
from senna.data.schema import AgentDecision, LapFrameRow, SimulationRun

router = APIRouter()


def frame_delay_s(lap_time_s: float, speed: int) -> float:
    return lap_time_s / speed


async def _run_row(engine, run_id: int):
    async with engine.connect() as conn:
        found = await conn.execute(
            select(SimulationRun).where(SimulationRun.id == run_id,
                                        SimulationRun.status.is_not(None))
        )
        return found.first()


async def _stored_race(engine, run_id: int) -> tuple[list[dict], dict[int, dict]]:
    async with engine.connect() as conn:
        frames = (await conn.execute(
            select(LapFrameRow.frame).where(LapFrameRow.run_id == run_id)
            .order_by(LapFrameRow.lap)
        )).scalars().all()
        cards = (await conn.execute(
            select(AgentDecision.lap_number, AgentDecision.decision)
            .where(AgentDecision.run_id == run_id)
        )).all()
    return list(frames), {lap: card for lap, card in cards}


@router.websocket("/ws/simulations/{run_id}")
async def stream_simulation(ws: WebSocket, run_id: int):
    await ws.accept()
    cfg = serving_config()
    engine = ws.app.state.engine
    speeds = set(cfg["playback"]["speeds"])

    try:
        while True:
            row = await _run_row(engine, run_id)
            if row is None:
                await ws.close(code=4404, reason=f"no simulation run {run_id}")
                return
            if row.status == "failed":
                await ws.send_json({"type": "sim:failed", "summary": row.summary})
                await ws.close()
                return
            if row.status == "complete":
                break
            await asyncio.sleep(cfg["ws"]["status_poll_s"])

        frames, cards = await _stored_race(engine, run_id)
        nominal_lap_s = (row.summary or {}).get("nominal_lap_s", 90.0)
        speed = min(speeds)  # 1x until the client says otherwise
        paused = False
        index = 0
        receive = asyncio.ensure_future(ws.receive_json())

        def handle(message: dict) -> int:
            nonlocal speed, paused
            kind = message.get("type")
            if kind == "client:speed" and message.get("speed") in speeds:
                speed = message["speed"]
            elif kind == "client:pause":
                paused = True
            elif kind == "client:seek":
                paused = False
                return max(0, min(int(message.get("lap", 1)) - 1, len(frames) - 1))
            return index

        while index < len(frames):
            if paused:
                # the clock stops dead: nothing is sent and playback_sleep is not
                # called again until a client message resumes or seeks
                index = handle(await receive)
                receive = asyncio.ensure_future(ws.receive_json())
                continue

            frame = frames[index]
            await ws.send_json({"type": "sim:lap", "frame": frame,
                                "card": cards.get(frame["lap"])})
            for event in frame["events"]:
                await ws.send_json({"type": "sim:event", **event})
            index += 1

            tick = asyncio.ensure_future(
                ws.app.state.playback_sleep(frame_delay_s(nominal_lap_s, speed))
            )
            done, _ = await asyncio.wait({receive, tick},
                                         return_when=asyncio.FIRST_COMPLETED)
            if receive in done:
                index = handle(receive.result())
                receive = asyncio.ensure_future(ws.receive_json())
            if not tick.done():
                if paused:
                    tick.cancel()
                else:
                    await tick

        await ws.send_json({"type": "sim:complete", "summary": row.summary})
        receive.cancel()
    except WebSocketDisconnect:
        # E-16: nothing to recover — the next socket replays from the same store
        return
