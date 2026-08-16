"""The 5.9.2 response and request shapes, verbatim. These models are the API's
contract with the frontend and the spec — change the spec before changing a shape
(api/CLAUDE.md). Most serving detail travels in the open dict fields (config, summary,
honesty) and in the X-Model-Version header. F12 is the exception: EnergyProfile and
DegradationCurve gain additive fields (usable_soc_mj, the typed EnergyLap, source_circuit,
cliff_age) recorded as an approved 5.9.2 divergence in docs/plans/F12-plan.md, the same
way F10 and F11 recorded theirs — additive only, so no existing consumer breaks.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SimulationCreate(BaseModel):
    # forbid, or a typo like "wether_profile" silently becomes a dry race
    model_config = ConfigDict(extra="forbid")

    circuit_id: str
    era: Literal["2024", "2026"] = "2026"
    grid_position: int = Field(ge=1, le=22)
    weather_profile: Literal["dry", "mixed", "wet_risk"] = "dry"
    # the env's own default is "train"; the API passes this explicitly every time
    # (plan divergence 2)
    rival_band: Literal["train", "test"] = "test"
    seed: int | None = None          # None -> drawn server-side, echoed back (5.9.2)
    model_version: str | None = None  # None -> the served MODEL_VERSION


class JobAccepted(BaseModel):
    run_id: int
    # set only by POST /counterfactuals: the replay leg of the pair (additive 5.9.2
    # divergence, F13 plan)
    baseline_run_id: int | None = None


class CarState(BaseModel):
    id: int                       # stable car index; the ego is 0 (liveries are F11's)
    s_track: float                # display-only lap fraction in [0, 1) — see frames.py
    position: int
    compound: str
    tyre_age: int
    gap_ahead_s: float | None     # None for the leader
    in_pit: bool


class AgentState(BaseModel):
    soc_mj: float
    harvest_mj: float
    deploy_mj: float
    mode: int
    action: dict
    reward_terms: dict
    mask_reasons: dict


class RaceEvent(BaseModel):
    kind: Literal["sc", "vsc", "red", "weather", "pit"]
    car_id: int | None = None
    detail: str | None = None


class LapFrame(BaseModel):
    lap: int
    cars: list[CarState]
    agent: AgentState
    events: list[RaceEvent]


class SimulationResult(BaseModel):
    run_id: int
    status: str
    model_version: str | None
    env_config_hash: str | None
    circuit_id: str | None
    era: str | None
    seed: int | None
    config: dict | None
    summary: dict | None
    created_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None


class DecisionCard(BaseModel):
    # the exact dict senna.explain.cards.build_card emits (5.8.3) passes through
    circuit: str
    lap: int
    track_status: str
    state: dict
    masks: dict
    action: dict
    decision: str
    probs: dict
    drivers: dict
    flip: list
    plain_language: str
    honesty: dict


class CircuitSummary(BaseModel):
    id: str
    race_laps: int
    h_max_mj: float               # per-event FIA recoverable-energy cap (E-02)
    coverage: dict                # computed from what is built, never asserted (E-13)


class CircuitDetail(CircuitSummary):
    compounds: dict               # era -> compound -> "native" | "transferred" (T5):
                                  # whether this circuit's tyre model was fitted here
                                  # or borrowed from a cluster donor


class RaceDetail(BaseModel):
    year: int
    round: int
    event_name: str
    results: list
    laps: list


class ModelVersion(BaseModel):
    version: str
    eval_points: float | None     # promotion.json mean_points (F08 selection)
    fidelity: dict | None         # per-head top-1 agreement (5.8.2 badge)
    config_hash: str
    promoted_at: str | None


class EnergyLap(BaseModel):
    lap: int
    harvest_mj: float
    deploy_mj: float
    soc_mj: float                 # clipped to [0, usable_soc_mj] in the sim (E-01)
    mode: int                     # 0-3: conserve, balanced, attack, defend
    pit: int                      # 0 = stayed out; 1-5 = pitted for compound code + 1


class EnergyProfile(BaseModel):
    run_id: int
    circuit_id: str
    h_max_mj: float               # per-event harvest cap, the bars panel's ceiling (E-02)
    usable_soc_mj: float          # the 4 MJ store, so the SOC axis is served not hardcoded
    laps: list[EnergyLap]


class DegradationCurve(BaseModel):
    circuit_id: str
    era: str
    compound: str
    a: float
    b: float
    low_confidence: bool
    max_age_seen: int | None
    n_laps: int | None
    source_circuit: str | None    # T5 cluster-transfer donors; None for a direct fit
    cliff_age: int                # the failure cliff the sim enforces (scenario.cliff_age_laps)
