"""F1RaceEnv — the Gymnasium environment at the heart of SENNA (spec 5.5).

Twenty-two cars, one decision per lap, MultiDiscrete([6, 4]) under action masking, the
transition dynamics of 5.5.3, and the three-term reward of 5.5.4. The agent drives one
ego car; the rest of the field runs the F06 archetypes (senna/env/rivals.py) — three
readable styles drawn per race from a train/test parameter split (E-06). Legality is
masks plus physics clipping, never a reward penalty (F-16), and every stochastic stream
hangs off the reset seed so a SubprocVecEnv worker is stateless (5.5.5).

Two optional keywords support the F06 deterministic twin (A-05/M3). record=True captures
every event a race applied into an EventTrace; twin=<trace> replays one, freezing the
events while the ego strategy varies — the ceiling the oracle regret metric measures
against, and the honest fix for the fact that a paired seed is not a paired race (the RNG
stream consumes a policy-dependent number of variates, so two policies diverge in their
events after the first different stop).
"""

import numpy as np
from gymnasium import Env
from gymnasium.spaces import Box, MultiDiscrete

from senna import config
from senna.env import dynamics, events, observation, reward_v2, rivals
from senna.env.engine import LapDecisions, advance_lap, begin_lap
from senna.env.events_io import (
    STAY_OUT,
    LiveSource,
    TraceSink,
    TraceSource,
    max_age_by_code,
)
from senna.env.masks import SLICK_ACTIONS, UNFITTED_COMPOUND, ActionMask, build_mask
from senna.env.observation import NO_DEG_A, NO_DEG_B
from senna.env.reward import pace_shaping, shaping_step, terminal_points
from senna.env.scenario import COMPOUNDS, START_COMPOUND, build_scenario, compound_code
from senna.env.state import RaceState
from senna.env.twin import EventTrace

_STATUS_NAMES = {events.GREEN: "green", events.VSC: "vsc", events.SC: "sc", events.RED: "red"}
_START_COMPOUND = compound_code(START_COMPOUND)


class F1RaceEnv(Env):
    metadata = {"render_modes": []}

    def __init__(self, circuit: str, era: str = "2026", *, rival_band: str = "train",
                 configs_dir=None, record: bool = False, twin: EventTrace | None = None,
                 solo: bool = False, weather: str = "markov", hazards: str = "full",
                 constraints: str = "mask", reward_mode: str = "v3", drivers=None):
        if weather not in ("markov", "dry"):
            raise ValueError(f"weather must be 'markov' or 'dry', not '{weather}'")
        if hazards not in ("full", "sc_vsc", "none"):
            raise ValueError(f"hazards must be 'full', 'sc_vsc' or 'none', not '{hazards}'")
        if constraints not in ("mask", "penalty"):
            raise ValueError(f"constraints must be 'mask' or 'penalty', not '{constraints}'")
        if reward_mode not in ("v3", "terminal_only", "v2"):
            raise ValueError(
                f"reward_mode must be 'v3', 'terminal_only' or 'v2', not '{reward_mode}'"
            )
        self.circuit = circuit
        self.era = era
        self.scenario = build_scenario(circuit, era, drivers=drivers, configs_dir=configs_dir)
        self.total_laps = self.scenario.total_laps
        self.n_cars = 1 if solo else self.scenario.grid_size
        self._solo = solo
        self._weather_mode = weather
        self._hazards = hazards
        self._constraints = constraints
        self._reward_mode = reward_mode
        # the ablation arms' constants load once here, never in the hot loop; the
        # default path does not read ablations.yaml at all (5.6.3 rows 2-3)
        ablations = (config.load("ablations", configs_dir)
                     if constraints == "penalty" or reward_mode == "v2" else None)
        self._violation_penalty = (float(ablations["penalty"]["violation_penalty"])
                                   if constraints == "penalty" else 0.0)
        self._v2 = ablations["reward_v2"] if reward_mode == "v2" else None
        if reward_mode == "v2":
            term_keys = ("pace", "position_gain", "position_loss", "terminal", "sc_pit",
                         "ers_efficiency", "grip_stint_end", "undercut", "ers_violation",
                         "fuel", "tyre_failure", "fastest_lap")
        else:
            term_keys = ("pace", "position", "terminal")
        if constraints == "penalty":
            term_keys = (*term_keys, "violation_penalty")
        self._term_keys = term_keys

        self.action_space = MultiDiscrete([6, 4])
        self.observation_space = Box(
            low=-1.0, high=1.0, shape=(observation.OBS_DIM,), dtype=np.float32
        )

        # the per-lap event constants now live on the event source (senna/env/events_io.py);
        # what stays here is what the adapter itself needs — the reward and the mask
        env_cfg = self.scenario.env
        self._w_p = env_cfg["reward"]["pace_weight_w_p"]
        self._coef = env_cfg["reward"]["position_potential_coef"]
        self._gamma = env_cfg["reward"]["gamma"]
        self._points = env_cfg["reward"]["points_2026"]
        self._divisor = env_cfg["reward"]["points_divisor"]

        self._band = rival_band
        if twin is not None:
            self._check_twin(twin)
        self._twin = twin
        self._record = record
        self._book = rivals.load_book(configs_dir, validity=env_cfg["compound_validity"])
        if rival_band not in self._book.bands:
            raise KeyError(
                f"no rival band '{rival_band}' — rivals.yaml defines: {', '.join(self._book.bands)}"
            )
        self._max_age_by_code = max_age_by_code(self.scenario)
        # F08 mask guard (INDEX 19 Jul): pit action = compound code + 1, slicks only —
        # the baselines already shop fitted compounds, this closes the same door on
        # the agent
        self._fitted_slick_actions = frozenset(
            compound_code(name) + 1 for name in self.scenario.available_compounds
        )

        self._state: RaceState | None = None
        self._mask: ActionMask | None = None
        self._rng = None
        self._rivals: rivals.RivalDraw | None = None
        self._trace: EventTrace | None = None
        self._sink: TraceSink | None = None
        self._source = None

    # -- gymnasium api ----------------------------------------------------------

    def _check_twin(self, trace: EventTrace) -> None:
        if trace.n_cars != self.n_cars or trace.n_laps != self.total_laps:
            raise ValueError(
                f"twin shape ({trace.n_laps} laps, {trace.n_cars} cars) does not match the "
                f"env ({self.total_laps} laps, {self.n_cars} cars) — a mismatched trace "
                "would misreplay mid-race instead of failing here"
            )

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if options and "twin" in options:
            # swap the replayed race without rebuilding the env — the Stage B eval replays
            # 200 traces per gate check, and construction re-parses every physics yaml
            self._check_twin(options["twin"])
            self._twin = options["twin"]
        pin = options.get("grid_position") if options else None
        if pin is not None and self._twin is not None:
            raise ValueError("grid_position cannot repin a twin replay — the trace owns the grid")
        self._rng = np.random.default_rng(seed)
        n = self.n_cars
        if pin is not None and not 1 <= pin <= n:
            raise ValueError(f"grid_position {pin} is outside this grid (1..{n})")

        if self._twin is not None:
            grid = self._twin.grid.copy()
            driver_s = self._twin.driver_s.copy()
        else:
            grid = self._rng.permutation(n) + 1  # a seeded starting order, ego is car 0
            if pin is not None:
                # swap rather than redraw: the field keeps its seeded order and every
                # later draw stays byte-identical to the unpinned stream (F10 serving)
                j = int(np.flatnonzero(grid == pin)[0])
                grid[0], grid[j] = int(grid[j]), int(grid[0])
            driver_s = self._rng.normal(0.0, self.scenario.sigma_driver_s, n)
            if self.scenario.lineup is not None:
                # draw first, then overwrite the named seats. Skipping the draw would move
                # every seeded race in the repo — the frozen model's evaluation, the Stage
                # B traces, F14 — and this way a named race is the same race as the
                # unnamed one at that seed, with people in it (F16's lesson, F17).
                named_s = self.scenario.lineup.seat_pace_s[:n]
                driver_s = np.where(np.isnan(named_s), driver_s, named_s)

        self._state = RaceState(
            n_cars=n,
            lap=0,
            compound=np.full(n, _START_COMPOUND),
            tyre_age=np.zeros(n, dtype=int),
            soc_mj=np.full(n, self.scenario.usable_soc_mj),
            fuel_kg=np.full(n, self.scenario.race_fuel_kg),
            cumulative_time_s=(grid - 1) * 1e-3,  # tiny offsets so lap-0 order is the grid
            grid_position=grid,
            pit_count=np.zeros(n, dtype=int),
            second_compound_used=np.zeros(n, dtype=bool),
            first_compound=np.full(n, _START_COMPOUND),
            last_harvest_mj=np.zeros(n),
            last_deploy_mj=np.zeros(n),
            retired=np.zeros(n, dtype=bool),
            driver_s=driver_s,
            track_status=events.GREEN,
            status_laps_left=0,
            weather=events.DRY,
            wetness=0.0,
            red_flags_seen=0,
            red_flag_now=False,
            ego=0,
        )

        # a live field draws its archetypes per race (E-06); a replayed one takes its
        # rivals verbatim from the trace, so no draw is made
        self._rivals = (
            None if self._twin is not None
            else rivals.draw_field(self._book, self._band, n_cars=n, ego=0, rng=self._rng)
        )
        # where this race's events come from. The drawn pace sigma rides the live source
        # because per-lap noise has been scaled by the archetype mix since F06.
        self._source = (
            TraceSource(self._twin, self.scenario, n_cars=n) if self._twin is not None
            else LiveSource(self.scenario, sigma_mult=self._rivals.sigma_mult,
                            hazards=self._hazards, weather=self._weather_mode)
        )
        self._ego_pit_laps: list[int] = []
        self._ego_pit_compounds: list[str] = []
        self._ego_derate_count = 0
        self._ego_derated_now = False
        self._ego_harvest_total = 0.0
        self._ego_deploy_total = 0.0
        self._forced_pit_now = False
        self._violations_this_lap: dict[str, int] = {}
        if self._reward_mode == "v2":
            self._sc_laps_active = 0
            self._field_fastest_s = np.inf
            self._ego_fastest_s = np.inf
            self._undercut_check: tuple[int, int] | None = None
        self._trace = self._new_trace(seed, grid, driver_s) if self._record else None
        self._sink = TraceSink(self._trace) if self._record else None

        self._mask = self._ego_mask()
        return self._observe(), self._info(dict.fromkeys((*self._term_keys, "total"), 0.0))

    def _new_trace(self, seed, grid, driver_s) -> EventTrace:
        trace = EventTrace.green(
            self.circuit, self.era, self.total_laps, self.n_cars,
            grid=grid.copy(), driver_s=driver_s.copy(),
        )
        trace.seed = -1 if seed is None else int(seed)
        return trace

    def recorded_trace(self) -> EventTrace:
        """The EventTrace captured during a record=True episode — the deterministic twin
        the oracle rolls against and the M5 afterstate metric branches from. Refuses an
        incomplete trace: a race that retired before the flag would leave a green-tailed
        twin that silently misrepresents the events (M3)."""
        if self._trace is None:
            raise RuntimeError("no trace recorded — build the env with record=True")
        if self._sink.laps_recorded < self.total_laps:
            raise RuntimeError(
                f"trace covers only {self._sink.laps_recorded}/{self.total_laps} laps — the "
                "recorded race did not reach the flag, so the twin is incomplete"
            )
        return self._trace

    def step(self, action):
        state = self._state
        lap_index = state.lap  # 0-based row for the record / replay trace
        prev_position = int(state.positions()[state.ego])
        prev_ahead_car = self._car_ahead() if self._reward_mode == "v2" else None
        pit_ego, mode_ego = self._coerce(action)
        # the executed (post-snap) action, kept for the serving frame — display honesty
        # wants what ran, not what was asked for (F10; snapped counts track the delta)
        self._ego_action = (pit_ego, mode_ego)

        context = begin_lap(state, self._rng, source=self._source, lap_index=lap_index)
        decisions = self._field_decisions(pit_ego, mode_ego, context, lap_index)
        outgoing = self._v2_before_lap() if self._reward_mode == "v2" else None
        outcome = advance_lap(state, context, decisions, self.scenario, self._rng,
                              source=self._source, sink=self._sink)

        self._log_ego_lap(outcome, decisions, lap_index)
        v2_lap = (self._v2_lap_facts(pit_ego, outcome, prev_ahead_car, outgoing, lap_index)
                  if self._reward_mode == "v2" else None)

        ego = state.ego
        terminated = bool(state.lap >= self.total_laps or state.retired[ego])
        # solo, the position and terminal terms are constants, so pit loss must enter
        # through the pace term or stops are free (5.7 Stage A; F07 decision 1)
        pace_time_s = (float(outcome.lap_time_s[ego]) if self._solo
                       else float(outcome.racing_time_s[ego]))
        terms = self._reward(prev_position, pace_time_s, terminated, v2_lap)
        self._mask = self._ego_mask()
        return self._observe(), terms["total"], terminated, False, self._info(terms)

    def _v2_before_lap(self) -> tuple[int, int]:
        """What ablation 3 has to read while the lap is still ahead of it: how long the
        safety car has been out, and the set the ego is about to finish the lap on — the
        pit swap moves compound and age, and v2 rewards the grip that came off."""
        state = self._state
        self._sc_laps_active = (self._sc_laps_active + 1
                                if state.track_status == events.SC else 0)
        return int(state.compound[state.ego]), int(state.tyre_age[state.ego])

    def _log_ego_lap(self, outcome, decisions, lap_index: int) -> None:
        """The ledger the info dict and the terminal summary read from. It is the adapter's
        because it is about one seat: the engine reported the whole field and has no view on
        which of the twenty-two anyone is watching."""
        ego = self._state.ego
        self._forced_pit_now = bool(outcome.failed[ego])
        if decisions.pit[ego] != STAY_OUT:
            self._ego_pit_laps.append(lap_index + 1)
            self._ego_pit_compounds.append(COMPOUNDS[int(decisions.pit[ego])])
        self._ego_harvest_total += float(outcome.harvest_mj[ego])
        self._ego_deploy_total += float(outcome.deploy_mj[ego])
        self._ego_derated_now = bool(outcome.derate_penalty_s[ego] > 0)
        if self._ego_derated_now:
            self._ego_derate_count += 1

    def _field_decisions(self, pit_ego: int, mode_ego: int, context, lap_index: int):
        """Fill all twenty-two seats. Rivals decide by their archetype rules (or replay the
        trace's applied choices) and hold balanced mode — a documented F06 simplification,
        since the E-06 axis is the pit response, not the energy mode. The ego's own heads
        are laid over the top, and from the engine's side no seat looks different."""
        state = self._state
        if self._twin is not None:
            pit = self._twin.rival_pit[lap_index].astype(int)
            mode = self._twin.rival_mode[lap_index].astype(int)
        else:
            pit = rivals.pit_choices(
                self._book, self._rivals, state, status_onset=context.onset,
                red_flag=context.red_flag, max_age_by_code=self._max_age_by_code,
                validity=self.scenario.env["compound_validity"],
                total_laps=self.total_laps, rng=self._rng,
            )
            mode = np.full(self.n_cars, dynamics.BALANCED)
        if pit_ego >= 1:
            pit[state.ego] = pit_ego - 1  # pit head 1..5 -> compound code 0..4
        mode[state.ego] = mode_ego
        return LapDecisions(pit=pit, mode=mode)

    @property
    def twin(self) -> EventTrace | None:
        """The trace this env is replaying, if any. The M5/M6 searches need it to ask what
        the mask would have allowed on a given lap, and reaching into a private for that
        would make every afterstate caller fragile to a rename."""
        return self._twin

    def action_masks(self) -> np.ndarray:
        if self._constraints == "penalty":
            # the learner sees no fence; the true mask still runs inside as the
            # violation detector (5.6.3 row 2)
            return np.ones_like(self._mask.flat())
        return self._mask.flat()

    # -- reward, observation, info ----------------------------------------------

    def _reward(self, prev_position: int, racing_time_s: float, terminated: bool,
                v2_lap: dict | None) -> dict:
        """The step's reward decomposition; total is always the exact sum of the other
        keys, in every mode — the contract the RewardTermsCallback iterates over."""
        state = self._state
        position = int(state.positions()[state.ego])
        dnf = bool(state.retired[state.ego])
        terminal = (terminal_points(position, self._points, self._divisor, dnf=dnf)
                    if terminated else 0.0)

        if self._reward_mode == "v2":
            terms = self._v2_terms(prev_position, position, racing_time_s, terminated,
                                   dnf, terminal, v2_lap)
        elif self._reward_mode == "terminal_only":
            terms = {"pace": 0.0, "position": 0.0, "terminal": terminal}
        else:
            terms = {
                "pace": pace_shaping(racing_time_s, self.scenario.t_ref_s,
                                     self.scenario.s_ref_s, self._w_p),
                "position": shaping_step(prev_position, position, self._coef, self._gamma),
                "terminal": terminal,
            }
        if self._constraints == "penalty":
            terms["violation_penalty"] = (self._violation_penalty
                                          * sum(self._violations_this_lap.values()))
        terms["total"] = sum(terms.values())
        return terms

    def _v2_terms(self, prev_position: int, position: int, racing_time_s: float,
                  terminated: bool, dnf: bool, terminal: float, lap_facts: dict) -> dict:
        v2 = self._v2
        gain, loss = reward_v2.position_change(
            prev_position, position, gain=v2["position_gain"], loss=v2["position_loss"]
        )
        holds_fastest = terminated and self._ego_fastest_s <= self._field_fastest_s
        return {
            # pace and terminal reuse v3's forms (ablations.yaml: the arm isolates
            # what v2 added); the ego's only retirement path is fuel exhaustion, so
            # a terminal DNF and the fuel penalty coincide by construction
            "pace": pace_shaping(racing_time_s, self.scenario.t_ref_s,
                                 self.scenario.s_ref_s, self._w_p),
            "position_gain": gain,
            "position_loss": loss,
            "terminal": terminal,
            "sc_pit": reward_v2.sc_pit_bonus(
                lap_facts["pitted"], lap_facts["sc_laps_active"], bonus=v2["sc_pit_bonus"],
                window_laps=v2["sc_pit_window_laps"],
            ),
            "ers_efficiency": reward_v2.ers_efficiency(
                lap_facts["deployed_mj"], self.scenario.e_dep_mj,
                coef=v2["ers_efficiency_coef"],
            ),
            "grip_stint_end": reward_v2.grip_stint_end(
                lap_facts["pitted"], lap_facts["outgoing_grip"], coef=v2["grip_stint_end_coef"]
            ),
            "undercut": reward_v2.undercut_success(
                self._undercut_resolved_ahead(), bonus=v2["undercut_bonus"]
            ),
            "ers_violation": reward_v2.ers_violation(
                lap_facts["derate_s"], penalty=v2["ers_violation_penalty"]
            ),
            "fuel": reward_v2.fuel_exhausted(
                terminated and dnf, penalty=v2["fuel_penalty"]
            ),
            "tyre_failure": reward_v2.tyre_failure(
                lap_facts["tyre_failed"], penalty=v2["tyre_failure_penalty"]
            ),
            "fastest_lap": reward_v2.fastest_lap_bonus(
                holds_fastest, position, bonus=v2["fastest_lap_bonus"],
                points_places=len(self._points),  # P1-P10 = the env.yaml points table
            ),
        }

    def _v2_lap_facts(self, pit_ego: int, outcome, prev_ahead_car: int | None,
                      outgoing: tuple[int, int], lap_index: int) -> dict:
        """v2's per-lap inputs, read off the finished lap. `outgoing` is the compound and
        age the ego carried into it, sampled before the engine ran because the stint-end
        grip this arm rewards belongs to the set that came off, not the one going on."""
        ego = self._state.ego
        pitted = pit_ego >= 1 and not bool(outcome.failed[ego])
        outgoing_compound, outgoing_age = outgoing
        name = COMPOUNDS[outgoing_compound]
        outgoing_grip = float(dynamics.grip_est(
            self.scenario.deg_a.get(name, NO_DEG_A),
            self.scenario.deg_b.get(name, NO_DEG_B),
            outgoing_age,
        ))
        self._field_fastest_s = min(self._field_fastest_s, float(outcome.racing_time_s.min()))
        self._ego_fastest_s = min(self._ego_fastest_s, float(outcome.racing_time_s[ego]))
        if pitted and prev_ahead_car is not None and self._undercut_check is None:
            # +1: lap_index is the pre-advance lap, and the window counts full laps
            # AFTER the stop lap — undercut_window_laps 3 means judged once laps
            # L+1..L+3 have run, exactly as the yaml comment reads
            self._undercut_check = (
                prev_ahead_car, lap_index + 1 + int(self._v2["undercut_window_laps"])
            )
        return {
            "pitted": pitted,
            "outgoing_grip": outgoing_grip,
            "deployed_mj": float(outcome.deploy_mj[ego]),
            "derate_s": float(outcome.derate_penalty_s[ego]),
            "tyre_failed": bool(outcome.failed[ego]),
            "sc_laps_active": self._sc_laps_active,
        }

    def _undercut_resolved_ahead(self) -> bool:
        """True on the lap a pending undercut window closes with the ego classified
        ahead of its pre-stop target; the pending check clears either way."""
        if self._undercut_check is None or self._state.lap < self._undercut_check[1]:
            return False
        target, _ = self._undercut_check
        self._undercut_check = None
        state = self._state
        if bool(state.retired[state.ego]) or bool(state.retired[target]):
            return False
        rank = state.positions()
        return int(rank[state.ego]) < int(rank[target])

    def _car_ahead(self) -> int | None:
        """The car classified directly ahead of the ego at this moment, or None for
        the leader — the target a v2 undercut is judged against."""
        state = self._state
        rank = state.positions()
        position = int(rank[state.ego])
        if position <= 1:
            return None
        by_rank = np.argsort(rank, kind="stable")
        return int(by_rank[position - 2])

    def _neighbours(self):
        state = self._state
        rank = state.positions()
        position = int(rank[state.ego])
        by_rank = np.argsort(rank, kind="stable")
        ahead = int(by_rank[position - 2]) if position > 1 else None
        behind = int(by_rank[position]) if position < self.n_cars else None
        time_ego = state.cumulative_time_s[state.ego]
        gap_ahead = time_ego - state.cumulative_time_s[ahead] if ahead is not None else 0.0
        gap_behind = state.cumulative_time_s[behind] - time_ego if behind is not None else 0.0
        return ahead, behind, float(gap_ahead), float(gap_behind)

    def _pit_open(self) -> bool:
        # the real pit lane stays open under SC and VSC — that is what makes the SC stop the
        # interesting decision (E-03/E-05); only a physical closure would shut it
        return self._state.track_status in (events.GREEN, events.VSC, events.SC, events.RED)

    def _ego_mask(self) -> ActionMask:
        state = self._state
        return build_mask(
            pit_open=self._pit_open(),
            weather=state.weather,
            wetness=state.wetness,
            soc_mj=float(state.soc_mj[state.ego]),
            lap=state.lap,
            total_laps=self.total_laps,
            second_compound_used=bool(state.second_compound_used[state.ego]),
            attack_soc_floor_mj=self.scenario.attack_soc_floor_mj,
            validity=self.scenario.env["compound_validity"],
            fitted_slick_actions=self._fitted_slick_actions,
        )

    def _coerce(self, action) -> tuple[int, int]:
        """Physics disposes. Masked, an illegal request snaps to a legal one, so the
        agent can never execute it (F-16). Under penalty constraints the request
        executes and is counted instead — v2's architecture, rebuilt for ablation 2
        (5.6.3) — except the unfitted-compound guard, a data limit no fine buys out."""
        pit, mode = int(action[0]), int(action[1])
        mask = self._mask
        self._violations_this_lap = {}
        if self._constraints == "penalty":
            return self._coerce_penalty(pit, mode)
        if not mask.mode[mode]:
            mode = dynamics.BALANCED
        if mask.pit[pit]:
            return pit, mode
        return self._snap_pit(pit), mode

    def _coerce_penalty(self, pit: int, mode: int) -> tuple[int, int]:
        mask = self._mask
        if not mask.mode[mode]:
            # attack on an empty store executes and derates anyway (E-01 clipping);
            # the fine is on the request, exactly v2's clip-plus-penalty
            self._count_violation(mask.reasons[f"mode:{mode}"])
        if mask.pit[pit]:
            return pit, mode
        reason = mask.reasons[f"pit:{pit}"]
        if pit in SLICK_ACTIONS and pit not in self._fitted_slick_actions:
            # the guard holds in every mode: the request is snapped, and it is fined
            # only when a sporting rule (not the data limit) was what forbade it
            if reason != UNFITTED_COMPOUND:
                self._count_violation(reason)
            return self._snap_pit(pit), mode
        self._count_violation(reason)
        return pit, mode

    def _count_violation(self, reason: str) -> None:
        self._violations_this_lap[reason] = self._violations_this_lap.get(reason, 0) + 1

    def _snap_pit(self, pit: int) -> int:
        mask = self._mask
        if mask.pit[0] and pit != 0:
            return 0  # asked for an unavailable compound; stay out
        first = COMPOUNDS[int(self._state.first_compound[self._state.ego])]
        compounds = [k for k in np.flatnonzero(mask.pit) if k != 0]
        fresh = [k for k in compounds if COMPOUNDS[k - 1] != first]
        return int((fresh or compounds)[0])

    def _observe(self) -> np.ndarray:
        ahead, behind, gap_ahead, gap_behind = self._neighbours()
        return observation.encode(
            self._state, self.scenario, gap_ahead_s=gap_ahead, gap_behind_s=gap_behind,
            ahead=ahead, behind=behind, pit_open=self._pit_open(),
        )

    def _info(self, terms: dict) -> dict:
        state = self._state
        ahead, behind, gap_ahead, gap_behind = self._neighbours()
        info = {
            "lap": state.lap,
            "position": int(state.positions()[state.ego]),
            "gap_ahead_s": gap_ahead,
            "gap_behind_s": gap_behind,
            "track_status": _STATUS_NAMES[state.track_status],
            "reward_terms": dict(terms),
            "violations": dict(self._violations_this_lap),
            "energy": {
                "harvest_mj": float(state.last_harvest_mj[state.ego]),
                "deploy_mj": float(state.last_deploy_mj[state.ego]),
                "soc_mj": float(state.soc_mj[state.ego]),
                "derated": self._ego_derated_now,  # M4 reports derates per lap, not just a total
            },
            "mask": {
                "pit": self._mask.pit.tolist(),
                "mode": self._mask.mode.tolist(),
                "reasons": self._mask.reasons,
            },
            "events": {
                "red_flag": bool(state.red_flag_now),
                "forced_pit": bool(self._forced_pit_now),
                "wetness": float(state.wetness),
                "weather": ("dry", "damp", "wet")[state.weather],
            },
        }
        if state.lap >= self.total_laps or state.retired[state.ego]:
            info.update(self._terminal_info())
        return info

    def _terminal_info(self) -> dict:
        state = self._state
        position = int(state.positions()[state.ego])
        dnf = bool(state.retired[state.ego])
        return {
            "final_position": position,
            "points": terminal_points(position, self._points, self._divisor, dnf=dnf),
            "race_time_s": float(state.cumulative_time_s[state.ego]),  # M3 is a time gap
            "dnf": dnf,
            "pit_laps": list(self._ego_pit_laps),
            "compounds": list(self._ego_pit_compounds),
            "derate_count": self._ego_derate_count,
            "energy_totals": {
                "harvest_mj": self._ego_harvest_total,
                "deploy_mj": self._ego_deploy_total,
            },
        }
