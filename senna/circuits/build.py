"""Build one GLTF ribbon per ingested circuit (spec 5.10.1, F04).

The battery walks every event that has an ingested session, picks the fastest
accurate lap of the most recent dry session, and runs it through the geometry
core: resample, smooth, frame, extrude, annotate. The loop is kept periodic
rather than sealed with a duplicate seam point, and the mesh closes the ring at
export. It writes a GLB plus a metadata sidecar per circuit and a build-time
index — the library is generated from the data, never a hand-listed calendar, so
Madrid appears the moment its first session lands (F-08, E-13).

Run it: python -m senna.circuits.build   (or `make circuits`)
"""

import argparse
import asyncio
import logging
import re
from pathlib import Path

import numpy as np
from sqlalchemy import select

from senna import config
from senna.circuits import annotations, elevation, export, geometry
from senna.circuits.sources import pick_most_recent_dry
from senna.data.db import database_url, engine_for
from senna.data.schema import Event, Session

log = logging.getLogger(__name__)


def slugify_event(event_name: str) -> str:
    """Event name to a filesystem slug ('Monaco Grand Prix' -> 'monaco_grand_prix')."""
    slug = re.sub(r"[^\w]+", "_", event_name.strip().lower(), flags=re.UNICODE)
    return slug.strip("_")


def circuit_index(entries: list[dict]) -> dict:
    """The generated library: circuits and a count computed from ingested entries (F-08)."""
    return {"circuits": list(entries), "count": len(entries)}


def build_ribbon(geometry_channels: dict, corners, ribbon_cfg: dict) -> tuple[np.ndarray, dict]:
    """Fastest-lap telemetry to ribbon vertices and metadata (the 5.10.1 seven steps)."""
    spacing_m = config.get(ribbon_cfg, "ribbon.resample_spacing_m")
    width_m = config.get(ribbon_cfg, "ribbon.width_m")
    clamp_fraction = config.get(ribbon_cfg, "ribbon.halfwidth_clamp_fraction")
    exaggeration = config.get(ribbon_cfg, "ribbon.elevation_exaggeration")
    camber_deg = config.get(ribbon_cfg, "ribbon.camber_deg")

    flat_z_epsilon_m = config.get(ribbon_cfg, "ribbon.flat_z_epsilon_m")

    raw = np.column_stack(
        [geometry_channels["x_m"], geometry_channels["y_m"], geometry_channels["z_m"]]
    )
    # resample leaves distinct stations (no duplicated start-finish point); the
    # loop is treated as periodic through smoothing, frames and radius, and the
    # mesh closes the ring at export — so the seam never sees a zero-length segment
    resampled = geometry.resample_by_arc_length(raw, spacing_m)
    station_count = len(resampled)

    plan_xy = geometry.savgol_smooth(
        resampled[:, :2],
        _fit_window(config.get(ribbon_cfg, "ribbon.savgol_window_xy"), station_count),
        config.get(ribbon_cfg, "ribbon.savgol_polyorder_xy"),
        closed=True,
    )

    if np.ptp(resampled[:, 2]) > flat_z_epsilon_m:
        smoothed_z = geometry.savgol_smooth(
            resampled[:, 2],
            _fit_window(config.get(ribbon_cfg, "ribbon.savgol_window_z"), station_count),
            config.get(ribbon_cfg, "ribbon.savgol_polyorder_z"),
            closed=True,
        )
        height_m, flags = elevation.elevation_profile(
            smoothed_z, exaggeration=exaggeration, camber_deg=camber_deg, n_points=station_count
        )
    else:
        height_m, flags = elevation.elevation_profile(
            None, exaggeration=exaggeration, camber_deg=camber_deg, n_points=station_count
        )

    centreline = np.column_stack([plan_xy, height_m])
    _, normals, _ = geometry.rotation_minimising_frames(centreline, closed=True)
    radius_m = geometry.curve_radius(centreline, closed=True)
    vertices = geometry.build_ribbon_vertices(
        centreline, normals, width_m / 2.0, radius_m, clamp_fraction
    )

    measured_length_m = geometry.lap_length_m(centreline, closed=True)
    # the lap's own odometer stands in for the published length, which we do not
    # have per circuit; the gate catches gross scale errors, not a true 5% audit
    odometer_m = float(geometry_channels["distance_m"].max())
    tolerance_pct = config.get(ribbon_cfg, "ribbon.lap_length_tolerance_pct")

    meta = {
        "lap_length_m": measured_length_m,
        "telemetry_distance_m": odometer_m,
        "lap_length_ok": geometry.within_tolerance(measured_length_m, odometer_m, tolerance_pct),
        "corners": annotations.corners_from_circuit_info(corners),
        "braking_zones": annotations.braking_zones(
            geometry_channels["distance_m"],
            geometry_channels["speed_kmh"],
            config.get(ribbon_cfg, "braking.speed_drop_kmh"),
            config.get(ribbon_cfg, "braking.window_m"),
        ),
        "xmode_sections": annotations.xmode_sections(
            geometry_channels["distance_m"],
            geometry_channels["throttle_pct"],
            config.get(ribbon_cfg, "xmode.full_throttle_pct"),
        ),
        "flags": {**flags, "xmode": "stylised"},
    }
    return vertices, meta


async def _ingested_sessions(conn) -> list[dict]:
    stmt = (
        select(
            Event.season,
            Event.round,
            Event.event_name,
            Session.session_name,
            Session.session_date_utc,
            Session.is_dry,
        )
        .join(Event, Session.event_id == Event.id)
        .order_by(Event.event_name, Session.session_date_utc)
    )
    return [dict(row) for row in (await conn.execute(stmt)).mappings().all()]


async def run_build(output_dir: Path) -> dict:
    ribbon_cfg = config.load("ribbon")
    ingest_cfg = config.load("ingest")
    zscore_max = config.get(ingest_cfg, "cleaning.pos_speed_zscore_max")

    from senna.data import fastf1_loader

    fastf1_loader.enable_cache(config.REPO_ROOT / config.get(ingest_cfg, "fastf1.cache_dir"))

    engine = engine_for(database_url())
    try:
        async with engine.connect() as conn:
            sessions = await _ingested_sessions(conn)
    finally:
        await engine.dispose()

    by_event: dict[str, list[dict]] = {}
    for session in sessions:
        by_event.setdefault(session["event_name"], []).append(session)

    entries = []
    for event_name, candidates in by_event.items():
        chosen = pick_most_recent_dry(candidates)
        if chosen is None:
            log.info("skip %s: no dry session ingested yet", event_name)
            continue

        channels, corners = fastf1_loader.load_fastest_lap_geometry(
            chosen["season"],
            chosen["round"],
            chosen["session_name"],
            zscore_max=zscore_max,
        )
        vertices, meta = build_ribbon(channels, corners, ribbon_cfg)
        slug = slugify_event(event_name)
        meta = {"slug": slug, "event_name": event_name, **meta}

        circuit_dir = output_dir / slug
        export.write_glb(circuit_dir / "ribbon.glb", vertices, closed=True)
        export.write_metadata(circuit_dir / "meta.json", meta)
        entries.append(
            {
                "slug": slug,
                "event_name": event_name,
                "has_elevation": meta["flags"]["source"] == "smoothed_z_exaggerated",
                "lap_length_ok": meta["lap_length_ok"],
            }
        )
        if not meta["lap_length_ok"]:
            log.warning(
                "%s: centreline %.0f m vs telemetry %.0f m exceeds %d%% (5.10.1 item 7)",
                slug,
                meta["lap_length_m"],
                meta["telemetry_distance_m"],
                config.get(ribbon_cfg, "ribbon.lap_length_tolerance_pct"),
            )
        log.info("built ribbon for %s", slug)

    index = circuit_index(entries)
    export.write_metadata(output_dir / "index.json", index)
    log.info("wrote %s (%d circuits)", output_dir / "index.json", index["count"])
    return index


def _fit_window(window: int, station_count: int) -> int:
    # Savitzky-Golay needs an odd window no longer than the series; short circuits
    # (or a sparse resample) shrink it rather than crash
    capped = min(window, station_count if station_count % 2 else station_count - 1)
    if capped % 2 == 0:
        capped -= 1
    return max(capped, 3)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build circuit ribbons (F04, spec 5.10.1)")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=config.REPO_ROOT / "data" / "circuits",
        help="where the per-circuit GLB/JSON and index.json are written",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(run_build(args.output_dir))


if __name__ == "__main__":
    main()
