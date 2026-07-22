"""WS /ws/simulations/{run_id} (5.9.3): a playback clock over stored frames, never a
re-simulation. The worker finishes the whole race before any client connects in
practice; a socket that arrives early subscribes to events:{run_id} and re-checks the
run row at ws.status_poll_s until the store is complete — bounded by the same
staleness rule the POST cache uses, so a dead work horse cannot hold a socket open
for days (E-16: the store, not the socket, is the source of truth).

The inter-frame sleep is app.state.playback_sleep so tests replay a 57-lap race in
milliseconds; 1x means one wall second per simulated second, so the delay divides the
circuit's fitted nominal lap time (worker summary) by the client's speed.
"""

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from api.deps import serving_config
from api.routes.simulations import run_is_stale
from senna.data.schema import AgentDecision, LapFrameRow, SimulationRun
from senna.serve.cache import events_channel

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


async def _await_completion(ws: WebSocket, run_id: int, cfg: dict):
    """The run row once complete, or None after this function closed the socket."""
    pubsub = ws.app.state.redis.pubsub()
    await pubsub.subscribe(events_channel(run_id))
    try:
        while True:
            row = await _run_row(ws.app.state.engine, run_id)
            if row is None:
                await ws.close(code=4404, reason=f"no simulation run {run_id}")
                return None
            if row.status == "complete":
                return row
            if row.status == "failed" or run_is_stale(row, queue_cfg=cfg["queue"]):
                await ws.send_json({"type": "sim:failed", "summary": row.summary})
                await ws.close()
                return None
            # the publish wakes this instantly; the timeout is only the re-check pace
            await pubsub.get_message(ignore_subscribe_messages=True,
                                     timeout=cfg["ws"]["status_poll_s"])
    finally:
        await pubsub.aclose()


@router.websocket("/ws/simulations/{run_id}")
async def stream_simulation(ws: WebSocket, run_id: int):
    await ws.accept()
    cfg = serving_config()
    speeds = set(cfg["playback"]["speeds"])
    receive = None

    try:
        row = await _await_completion(ws, run_id, cfg)
        if row is None:
            return

        frames, cards = await _stored_race(ws.app.state.engine, run_id)
        nominal_lap_s = (row.summary or {}).get("nominal_lap_s")
        if nominal_lap_s is None:
            # a complete run always carries its fitted lap time; inventing a tempo
            # here would be an unprovenanced constant (interpretability contract)
            await ws.close(code=4500, reason="run summary lacks nominal_lap_s")
            return

        speed = min(speeds)  # 1x until the client says otherwise
        paused = False
        index = 0
        receive = asyncio.ensure_future(ws.receive_json())

        def client_message(fut):
            try:
                return fut.result()
            except json.JSONDecodeError:
                return None  # malformed input is ignored, never a server traceback

        def handle(message) -> bool:
            """Apply a client message; True when the current tick must be cancelled
            so the change takes effect now, not a lap from now."""
            nonlocal speed, paused, index
            if not isinstance(message, dict):
                return False
            kind = message.get("type")
            if kind == "client:speed" and message.get("speed") in speeds:
                speed = message["speed"]
                return True
            if kind == "client:pause":
                paused = True
                return True
            if kind == "client:seek":
                try:
                    lap = int(message.get("lap", 1))
                except (TypeError, ValueError):
                    return False
                paused = False
                index = max(0, min(lap - 1, len(frames) - 1))
                return True
            return False

        while index < len(frames):
            if paused:
                # the clock stops dead: no frames, and playback_sleep is not called
                # again until a client message resumes or seeks
                await asyncio.wait({receive})
                handle(client_message(receive))
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
            interrupted = False
            if receive in done:
                interrupted = handle(client_message(receive))
                receive = asyncio.ensure_future(ws.receive_json())
            if interrupted:
                # at 1x a tick is a whole lap of wall clock — a seek or speed
                # change that waited it out would make scrubbing unusable (E-16)
                tick.cancel()
            elif not tick.done():
                await tick

        await ws.send_json({"type": "sim:complete", "summary": row.summary})
    except WebSocketDisconnect:
        # E-16: nothing to recover — the next socket replays from the same store
        return
    finally:
        if receive is not None:
            receive.cancel()
