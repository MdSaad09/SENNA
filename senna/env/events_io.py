"""Where a lap's events come from, and where they go (F16).

The tick asks four questions it cannot answer from the physics alone: what is the track
doing, is it raining, whose tyre let go, and how long did the pit crew take. A live race
rolls those from the per-circuit hazards; a twin replays them from a recorded trace so
the field's events stay frozen while the ego's strategy varies (A-05), which is what
makes the oracle regret a clean ceiling (M3).

Before F16 that choice was seven `if self._twin is not None` branches scattered through
the tick, so the physics could not be read without reading the replay logic threaded
through it. Here it is one seam: a source answers the four questions, a sink writes the
answers down, and senna/env/engine.py knows about neither beyond the calls below.

Draw order is the seed (5.5.5). Every method that consumes rng does so at exactly the
point in the lap `F1RaceEnv.step()` consumed it before the extraction, and TraceSource
deliberately draws nothing — a replayed race must not move the stream.
"""

import numpy as np

from senna.env import events
from senna.env.dynamics import BALANCED
from senna.env.scenario import COMPOUNDS

STAY_OUT = -1  # the pit head's "stay out", and what a trace stores for a car that did not box


def _max_age_by_code(scenario) -> np.ndarray:
    """Each compound's cliff age, in compound-code order, with the observation's age
    normaliser standing in for a compound the F02 fitter never saw."""
    fallback = scenario.env["obs"]["tyre_age_norm_laps"]
    return np.array([scenario.deg_max_age.get(name, fallback) for name in COMPOUNDS])


class LiveSource:
    """A race rolling its own events from the circuit's fitted hazards.

    `sigma_mult` is the per-car pace-noise scale the F06 field draw produced: rivals are
    dispersed by their archetype, the ego runs at unit sigma. It is passed in rather than
    derived because the engine has no opinion on who is driving — the asymmetry belongs
    to field construction, which is what lets the tick itself stay seat-symmetric.
    """

    def __init__(self, scenario, *, sigma_mult, hazards: str = "full", weather: str = "markov"):
        self.scenario = scenario
        self.sigma_mult = sigma_mult
        self._hazards = hazards
        self._weather_mode = weather

        env_cfg = scenario.env
        self._markov = env_cfg["weather"]["markov"]
        self._n_sectors = env_cfg["weather"]["n_sectors"]
        self._weather_targets = env_cfg["weather"]["target_wetness"]
        self._sc_laps = env_cfg["events"]["sc_duration_laps"]
        self._vsc_laps = env_cfg["events"]["vsc_duration_laps"]
        # the red flag first appears in the Stage C row of 5.7, so "sc_vsc" zeroes the cap
        self._max_red = env_cfg["events"]["red_flag_max_per_race"] if hazards == "full" else 0
        self._cliff_margin = env_cfg["tyre_failure"]["cliff_age_margin_laps"]
        self._tyre_hazard = env_cfg["tyre_failure"]["hazard_per_lap_beyond_cliff"]
        self._max_age_by_code = _max_age_by_code(scenario)

    def track_status(self, state, lap_index: int, rng) -> tuple[bool, int]:
        """Count a running neutralisation down, or roll for a new one. Returns the red-flag
        event flag (E-04, consumed this lap) and the neutralisation that began this lap —
        GREEN on a countdown lap, since only an onset offers a fresh pit decision."""
        if self._hazards == "none":
            return False, events.GREEN  # no roll, so the RNG stream is untouched
        if state.status_laps_left > 0:
            state.status_laps_left -= 1
            if state.status_laps_left == 0:
                state.track_status = events.GREEN
            return False, events.GREEN
        if state.track_status != events.GREEN:
            state.track_status = events.GREEN

        drawn = events.advance_track_status(events.GREEN, self.scenario.hazards, rng)
        if drawn == events.RED and state.red_flags_seen < self._max_red:
            state.red_flags_seen += 1
            state.track_status = events.RED
            return True, events.GREEN
        if drawn == events.SC:
            state.track_status = events.SC
            state.status_laps_left = self._sc_laps
            return False, events.SC
        if drawn == events.VSC:
            state.track_status = events.VSC
            state.status_laps_left = self._vsc_laps
            return False, events.VSC
        return False, events.GREEN

    def weather(self, state, lap_index: int, rng) -> None:
        if self._weather_mode == "dry":
            return  # pinned DRY/0.0 at the grid; no Markov roll, so no RNG draw
        state.weather, state.wetness = events.advance_weather(
            state.weather, state.wetness, self._markov, self._n_sectors, rng,
            target_wetness=self._weather_targets,
        )

    def failures(self, state, lap_index: int, rng) -> np.ndarray:
        """One roll per car, in seat order. Vectorising this into a single draw of shape
        (n_cars,) would consume the stream differently and move every seeded race, so the
        loop is load-bearing rather than an oversight (F16)."""
        failed = np.zeros(state.n_cars, dtype=bool)
        for car in range(state.n_cars):
            max_age = self._max_age_by_code[int(state.compound[car])]
            if self._hazards == "none":
                # deterministic Stage A: the twin's hard cap at the cliff, not a hazard roll
                failed[car] = state.tyre_age[car] > max_age + self._cliff_margin
            else:
                failed[car] = events.tyre_failure(
                    int(state.tyre_age[car]), max_age, self._cliff_margin,
                    self._tyre_hazard, rng,
                )
        return failed

    def lap_noise(self, state, rng) -> np.ndarray:
        return rng.normal(0.0, self.scenario.s_ref_s * self.sigma_mult)

    def pit_service_s(self, n_stopping: int, rng) -> np.ndarray:
        return rng.normal(
            self.scenario.pit_loss_mean_s, self.scenario.pit_loss_sigma_s, n_stopping
        )


class TraceSource:
    """A race replaying a recorded one. Every event is read rather than drawn, so the
    field's race is identical however the ego drives (A-05).

    Deliberately ego-aware, and the only part of the seam that is: the ego's tyre failure
    is recomputed from its own age because a replayed strategy can run a stint the
    recording never ran, and pit service is the fitted mean with no noise because
    deterministic physics is what makes the oracle regret a clean ceiling (M3).
    """

    def __init__(self, trace, scenario, *, n_cars: int):
        if trace.n_cars != n_cars or trace.n_laps != scenario.total_laps:
            raise ValueError(
                f"twin shape ({trace.n_laps} laps, {trace.n_cars} cars) does not match the "
                f"race ({scenario.total_laps} laps, {n_cars} cars) — a mismatched trace "
                "would misreplay mid-race instead of failing here"
            )
        self.trace = trace
        self.scenario = scenario
        self._cliff_margin = scenario.env["tyre_failure"]["cliff_age_margin_laps"]
        self._max_age_by_code = _max_age_by_code(scenario)

    def track_status(self, state, lap_index: int, rng) -> tuple[bool, int]:
        state.track_status = int(self.trace.status[lap_index])
        red = bool(self.trace.red_flag[lap_index])
        if red:
            state.red_flags_seen += 1
        return red, events.GREEN

    def weather(self, state, lap_index: int, rng) -> None:
        state.weather = int(self.trace.weather[lap_index])
        state.wetness = float(self.trace.wetness[lap_index])

    def failures(self, state, lap_index: int, rng) -> np.ndarray:
        failed = self.trace.failed[lap_index].copy()
        ego = state.ego
        cliff = self._max_age_by_code[int(state.compound[ego])] + self._cliff_margin
        failed[ego] = state.tyre_age[ego] > cliff
        return failed

    def lap_noise(self, state, rng) -> np.ndarray:
        return np.zeros(state.n_cars)

    def pit_service_s(self, n_stopping: int, rng) -> np.ndarray:
        return np.full(n_stopping, self.scenario.pit_loss_mean_s)


class TraceSink:
    """Writes each lap's events into a pre-allocated EventTrace — what `record=True`
    captures so a live race can be replayed as a twin afterwards.

    Ego-aware for the same reason TraceSource is: the ego's own pit and mode are blanked
    out of the recording, because on replay it drives from its action rather than from
    the trace. Recording them would pin the strategy the twin exists to vary.
    """

    def __init__(self, trace):
        self.trace = trace
        self.laps_recorded = 0

    def capture(self, state, context, decisions, failed) -> None:
        lap_index = context.lap_index
        trace = self.trace
        trace.status[lap_index] = state.track_status
        trace.red_flag[lap_index] = context.red_flag
        trace.weather[lap_index] = state.weather
        trace.wetness[lap_index] = state.wetness
        trace.failed[lap_index] = failed

        rival_pit = decisions.pit.copy()
        rival_pit[state.ego] = STAY_OUT
        trace.rival_pit[lap_index] = rival_pit
        rival_mode = decisions.mode.copy()
        rival_mode[state.ego] = BALANCED
        trace.rival_mode[lap_index] = rival_mode
        self.laps_recorded = lap_index + 1
