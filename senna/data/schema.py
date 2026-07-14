"""Postgres schema — the flagged superset, never a cleaned subset.

5.3.4 keeps in/out laps for pit timing and non-green laps for event-rate
fits, so ingest stores every row plus derived flags and the fits filter at
query time. Base tables follow the columns 5.3.2/5.3.3 consume; the 5.3.5
deltas (era/source flags, simulated-energy columns, JSONB decisions) are
built in from the start.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("season", "round"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    season: Mapped[int]
    round: Mapped[int]
    event_name: Mapped[str]
    event_format: Mapped[str | None]
    event_date: Mapped[datetime | None]


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (UniqueConstraint("event_id", "session_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    session_name: Mapped[str]
    session_date_utc: Mapped[datetime | None]
    openf1_session_key: Mapped[int | None]
    openf1_meeting_key: Mapped[int | None]
    missing_channels: Mapped[list | None] = mapped_column(JSONB)


class Lap(Base):
    __tablename__ = "laps"
    __table_args__ = (UniqueConstraint("session_id", "driver_number", "lap_number", "source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"))
    driver: Mapped[str | None]
    driver_number: Mapped[str]
    team: Mapped[str | None]
    lap_number: Mapped[int]
    stint: Mapped[int | None]
    compound: Mapped[str | None]
    tyre_life: Mapped[float | None]
    fresh_tyre: Mapped[bool | None]
    lap_time_s: Mapped[float | None]  # NaT stays null — never imputed for fits (5.3.4)
    lap_time_imputed: Mapped[bool] = mapped_column(default=False)
    sector1_s: Mapped[float | None]
    sector2_s: Mapped[float | None]
    sector3_s: Mapped[float | None]
    speed_st_kmh: Mapped[float | None]
    position: Mapped[int | None]
    track_status: Mapped[str | None]
    is_accurate: Mapped[bool | None]
    is_green: Mapped[bool | None]  # whole lap status 1 (5.3.4), derived at ingest
    pit_in_time_s: Mapped[float | None]
    pit_out_time_s: Mapped[float | None]
    lap_start_time_s: Mapped[float | None]
    era: Mapped[str]  # which physics yaml governs this row: "2024" or "2026"
    source: Mapped[str]  # real_2022 ... real_2026 / synthetic_2026 (5.3.5)
    energy_deployed_mj: Mapped[float | None]  # simulated rows only (5.3.5)
    energy_harvested_mj: Mapped[float | None]
    soc_end_mj: Mapped[float | None]


class WeatherSample(Base):
    __tablename__ = "weather"
    __table_args__ = (UniqueConstraint("session_id", "time_s"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"))
    time_s: Mapped[float]
    air_temp_c: Mapped[float | None]
    track_temp_c: Mapped[float | None]
    humidity_pct: Mapped[float | None]
    rainfall: Mapped[bool | None]
    wind_speed_ms: Mapped[float | None]


class RaceControlMessage(Base):
    # no natural key — real feeds repeat messages, so idempotency comes from
    # the delete-and-reload transaction, not a constraint
    __tablename__ = "race_control"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"))
    time_utc: Mapped[datetime | None]
    category: Mapped[str | None]
    flag: Mapped[str | None]
    status: Mapped[str | None]
    message: Mapped[str | None]
    lap: Mapped[int | None]


class SessionResult(Base):
    __tablename__ = "results"
    __table_args__ = (UniqueConstraint("session_id", "driver_abbrev"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"))
    driver_abbrev: Mapped[str]
    team_name: Mapped[str | None]
    grid_position: Mapped[int | None]
    position: Mapped[int | None]
    status: Mapped[str | None]
    points: Mapped[float | None]


class OpenF1PitStop(Base):
    __tablename__ = "openf1_pit_stops"
    __table_args__ = (UniqueConstraint("session_id", "driver_number", "lap_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"))
    driver_number: Mapped[int]
    lap_number: Mapped[int]
    pit_duration_s: Mapped[float | None]


class OpenF1Stint(Base):
    __tablename__ = "openf1_stints"
    __table_args__ = (UniqueConstraint("session_id", "driver_number", "stint_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"))
    driver_number: Mapped[int]
    stint_number: Mapped[int]
    compound: Mapped[str | None]
    lap_start: Mapped[int | None]
    lap_end: Mapped[int | None]
    tyre_age_at_start: Mapped[int | None]


class SimulationRun(Base):
    # minimal on purpose: F01 owns the table so the initial migration is the
    # whole schema; F10 migrates in what serving needs (E-15 cache keys live here)
    __tablename__ = "simulation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime]
    env_config_hash: Mapped[str | None]
    model_version: Mapped[str | None]
    config: Mapped[dict | None] = mapped_column(JSONB)


class AgentDecision(Base):
    __tablename__ = "agent_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("simulation_runs.id"))
    lap_number: Mapped[int]
    # one JSONB per decision: state, masks with reasons, action, probs, shap top-k (5.3.5)
    decision: Mapped[dict] = mapped_column(JSONB)


class IngestCheckpoint(Base):
    __tablename__ = "ingest_checkpoints"
    __table_args__ = (UniqueConstraint("season", "round", "source", "session_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    season: Mapped[int]
    round: Mapped[int]
    event_name: Mapped[str | None]
    source: Mapped[str]  # fastf1 / openf1 — which client owns the fetch
    session_name: Mapped[str]
    state: Mapped[str]  # pending -> loaded | failed | excluded
    rows_loaded: Mapped[int | None]
    error: Mapped[str | None]
    excluded_reason: Mapped[str | None]
    updated_at: Mapped[datetime]
