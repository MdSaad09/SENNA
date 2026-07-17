"""F1RaceEnv — the Gymnasium environment at the heart of SENNA (spec 5.5).

Twenty-two cars, one decision per lap, MultiDiscrete([6, 4]) under action masking, the
transition dynamics of 5.5.3, and the three-term reward of 5.5.4. The agent drives one
ego car; the rest of the field is the F05 placeholder — an equal-pace grid on a scripted
one-stop, replaced by real archetypes in F06. Legality is masks plus physics clipping,
never a reward penalty (F-16), and every stochastic stream hangs off the reset seed so a
SubprocVecEnv worker is stateless (5.5.5).
"""

import numpy as np
from gymnasium import Env
from gymnasium.spaces import Box, MultiDiscrete

from senna.env import dynamics, events, observation
from senna.env.masks import ActionMask, build_mask
from senna.env.pitlane import resolve_pit_lane
from senna.env.reward import RewardTerms, pace_shaping, shaping_step, terminal_points
from senna.env.scenario import COMPOUNDS, build_scenario, compound_code
from senna.env.state import RaceState

_STATUS_NAMES = {events.GREEN: "green", events.VSC: "vsc", events.SC: "sc", events.RED: "red"}
_BALANCED = 1
_START_COMPOUND = compound_code("MEDIUM")
_RIVAL_SECOND_COMPOUND = compound_code("HARD")


class F1RaceEnv(Env):
    metadata = {"render_modes": []}

    def __init__(self, circuit: str, era: str = "2026", *, configs_dir=None):
        self.circuit = circuit
        self.era = era
        self.scenario = build_scenario(circuit, era, configs_dir=configs_dir)
        self.total_laps = self.scenario.total_laps
        self.n_cars = self.scenario.grid_size

        self.action_space = MultiDiscrete([6, 4])
        self.observation_space = Box(
            low=-1.0, high=1.0, shape=(observation.OBS_DIM,), dtype=np.float32
        )

        env_cfg = self.scenario.env
        self._markov = env_cfg["weather"]["markov"]
        self._n_sectors = env_cfg["weather"]["n_sectors"]
        self._weather_targets = env_cfg["weather"]["target_wetness"]
        self._sc_laps = env_cfg["events"]["sc_duration_laps"]
        self._vsc_laps = env_cfg["events"]["vsc_duration_laps"]
        self._max_red = env_cfg["events"]["red_flag_max_per_race"]
        self._tyre_penalty_s = env_cfg["forced_pit"]["tyre_failure_penalty_s"]
        self._cliff_margin = env_cfg["tyre_failure"]["cliff_age_margin_laps"]
        self._tyre_hazard = env_cfg["tyre_failure"]["hazard_per_lap_beyond_cliff"]
        self._pit_loss_mult = env_cfg["pit_loss_mult"]
        self._min_service_s = env_cfg["pit"]["min_service_s"]
        self._lane_gap_s = env_cfg["pit"]["lane_gap_s"]
        self._w_p = env_cfg["reward"]["pace_weight_w_p"]
        self._coef = env_cfg["reward"]["position_potential_coef"]
        self._gamma = env_cfg["reward"]["gamma"]
        self._points = env_cfg["reward"]["points_2026"]
        self._divisor = env_cfg["reward"]["points_divisor"]

        self._state: RaceState | None = None
        self._mask: ActionMask | None = None
        self._rng = None

    # -- gymnasium api ----------------------------------------------------------

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._rng = np.random.default_rng(seed)
        n = self.n_cars

        grid = self._rng.permutation(n) + 1  # a seeded starting order, ego is car 0
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
            driver_s=self._rng.normal(0.0, self.scenario.sigma_driver_s, n),
            track_status=events.GREEN,
            status_laps_left=0,
            weather=events.DRY,
            wetness=0.0,
            red_flags_seen=0,
            red_flag_now=False,
            ego=0,
        )

        # the placeholder field: each rival takes one stop to a second compound mid-race
        centre = max(1, self.total_laps // 2)
        self._rival_pit_lap = self._rng.integers(centre - 3, centre + 4, size=n)
        self._ego_pit_laps: list[int] = []
        self._ego_pit_compounds: list[str] = []
        self._ego_derate_count = 0
        self._ego_harvest_total = 0.0
        self._ego_deploy_total = 0.0
        self._forced_pit_now = False

        self._mask = self._ego_mask()
        return self._observe(), self._info(RewardTerms(0.0, 0.0, 0.0, 0.0))

    def step(self, action):
        state = self._state
        prev_position = int(state.positions()[state.ego])
        pit_ego, mode_ego = self._coerce(action)

        red_flag = self._advance_track_status()
        state.weather, state.wetness = events.advance_weather(
            state.weather, state.wetness, self._markov, self._n_sectors, self._rng,
            target_wetness=self._weather_targets,
        )

        modes = np.full(self.n_cars, _BALANCED)
        modes[state.ego] = mode_ego
        pit_choice = self._field_pit_choices(pit_ego, red_flag)
        failed = self._tyre_failures()
        self._forced_pit_now = bool(failed[state.ego])

        gap_ahead = self._gaps_ahead()
        harvest = dynamics.per_lap_harvest_mj(self.scenario)
        harvest_mj = np.full(self.n_cars, harvest)
        request = dynamics.deploy_request_mj(modes, self.scenario)
        delivered, derate, soc_next = dynamics.resolve_energy(
            state.soc_mj, harvest_mj, request, self.scenario
        )

        noise = self._rng.normal(0.0, self.scenario.s_ref_s, self.n_cars)
        racing_time = dynamics.lap_time_s(
            compound=state.compound, age=state.tyre_age, fuel_kg=state.fuel_kg, modes=modes,
            delivered_mj=delivered, request_mj=request, derate_s=derate, gap_ahead_s=gap_ahead,
            wetness=state.wetness, track_status=np.full(self.n_cars, state.track_status),
            driver_s=state.driver_s, noise_s=noise, scenario=self.scenario,
        )
        pit_time = self._pit_times(pit_choice, failed, red_flag)
        lap_time = racing_time + pit_time

        self._apply_pits(pit_choice, failed, red_flag)
        state.cumulative_time_s = state.cumulative_time_s + lap_time
        state.tyre_age = np.where((pit_choice >= 0) | failed | red_flag, 0, state.tyre_age + 1)
        state.soc_mj = soc_next
        state.last_harvest_mj = harvest_mj
        state.last_deploy_mj = delivered
        state.fuel_kg = self._burn_fuel()
        state.retired |= state.fuel_kg <= 0.0
        state.lap += 1
        state.red_flag_now = red_flag
        if state.track_status == events.RED:
            state.track_status = events.GREEN  # the race resumes after the neutralisation

        ego = state.ego
        self._ego_harvest_total += float(harvest_mj[ego])
        self._ego_deploy_total += float(delivered[ego])
        if derate[ego] > 0:
            self._ego_derate_count += 1

        terminated = bool(state.lap >= self.total_laps or state.retired[ego])
        terms = self._reward(prev_position, float(racing_time[ego]), terminated)
        self._mask = self._ego_mask()
        return self._observe(), terms.total, terminated, False, self._info(terms)

    def action_masks(self) -> np.ndarray:
        return self._mask.flat()

    # -- events -----------------------------------------------------------------

    def _advance_track_status(self) -> bool:
        """Count a running neutralisation down, or roll for a new one. A red flag is
        returned as an event flag (E-04) and the state is consumed this lap."""
        state = self._state
        if state.status_laps_left > 0:
            state.status_laps_left -= 1
            if state.status_laps_left == 0:
                state.track_status = events.GREEN
            return False
        if state.track_status != events.GREEN:
            state.track_status = events.GREEN

        drawn = events.advance_track_status(events.GREEN, self.scenario.hazards, self._rng)
        if drawn == events.RED and state.red_flags_seen < self._max_red:
            state.red_flags_seen += 1
            state.track_status = events.RED
            return True
        if drawn == events.SC:
            state.track_status = events.SC
            state.status_laps_left = self._sc_laps
        elif drawn == events.VSC:
            state.track_status = events.VSC
            state.status_laps_left = self._vsc_laps
        return False

    def _tyre_failures(self) -> np.ndarray:
        state = self._state
        failed = np.zeros(self.n_cars, dtype=bool)
        for car in range(self.n_cars):
            name = COMPOUNDS[int(state.compound[car])]
            age_fallback = self.scenario.env["obs"]["tyre_age_norm_laps"]
            max_age = self.scenario.deg_max_age.get(name, age_fallback)
            failed[car] = events.tyre_failure(
                int(state.tyre_age[car]), max_age, self._cliff_margin, self._tyre_hazard, self._rng
            )
        return failed

    # -- pit choices and timing -------------------------------------------------

    def _field_pit_choices(self, pit_ego: int, red_flag: bool) -> np.ndarray:
        """Compound code each car pits to this lap, or -1 for staying out. Rivals take
        their one scheduled stop; a red flag hands everyone a free change (E-04)."""
        state = self._state
        choice = np.full(self.n_cars, -1)
        due = self._rival_pit_lap == (state.lap + 1)
        for car in range(self.n_cars):
            if car != state.ego and due[car] and state.pit_count[car] == 0:
                choice[car] = _RIVAL_SECOND_COMPOUND
        if pit_ego >= 1:
            choice[state.ego] = pit_ego - 1  # pit head 1..5 -> compound code 0..4
        if red_flag:
            for car in range(self.n_cars):
                if choice[car] < 0 and car != state.ego:
                    choice[car] = _RIVAL_SECOND_COMPOUND  # rivals take the free harder set
        return choice

    def _pit_times(self, pit_choice: np.ndarray, failed: np.ndarray, red_flag: bool) -> np.ndarray:
        """Green pit loss with FIFO stacking for scheduled stops (E-05); a flat penalty for
        a tyre-failure stop (+25 s, kept from v2); free under a red flag (E-04)."""
        state = self._state
        pit_time = np.zeros(self.n_cars)
        stopping = (pit_choice >= 0) & ~failed
        if not red_flag and stopping.any():
            cars = np.flatnonzero(stopping)
            draws = self._rng.normal(
                self.scenario.pit_loss_mean_s, self.scenario.pit_loss_sigma_s, cars.size
            )
            service = np.maximum(self._min_service_s, draws) * self._status_pit_multiplier()
            exit_s = resolve_pit_lane(
                state.cumulative_time_s[cars], service, lane_gap_s=self._lane_gap_s
            )
            pit_time[cars] = exit_s - state.cumulative_time_s[cars]
        pit_time[failed] = self._tyre_penalty_s
        return pit_time

    def _status_pit_multiplier(self) -> float:
        if self._state.track_status == events.SC:
            return self._pit_loss_mult["sc"]
        if self._state.track_status == events.VSC:
            return self._pit_loss_mult["vsc"]
        return 1.0

    def _apply_pits(self, pit_choice: np.ndarray, failed: np.ndarray, red_flag: bool) -> None:
        state = self._state
        changed = pit_choice >= 0
        state.compound = np.where(changed, pit_choice, state.compound)
        stopped = changed | failed | red_flag
        new_compound = state.compound != state.first_compound
        state.second_compound_used |= stopped & new_compound
        state.pit_count += (changed | failed).astype(int)
        if pit_choice[state.ego] >= 0:
            self._ego_pit_laps.append(state.lap + 1)
            self._ego_pit_compounds.append(COMPOUNDS[int(pit_choice[state.ego])])

    def _burn_fuel(self) -> np.ndarray:
        base = self.scenario.race_fuel_kg / self.total_laps
        if self._state.track_status in (events.SC, events.VSC):
            base *= self.scenario.sc_burn_factor
        return np.maximum(0.0, self._state.fuel_kg - base)

    # -- reward, gaps, observation, info ---------------------------------------

    def _reward(self, prev_position: int, racing_time_s: float, terminated: bool) -> RewardTerms:
        state = self._state
        position = int(state.positions()[state.ego])
        pace = pace_shaping(racing_time_s, self.scenario.t_ref_s, self.scenario.s_ref_s, self._w_p)
        shape = shaping_step(prev_position, position, self._coef, self._gamma)
        terminal = 0.0
        if terminated:
            dnf = bool(state.retired[state.ego])
            terminal = terminal_points(position, self._points, self._divisor, dnf=dnf)
        total = pace + shape + terminal
        return RewardTerms(pace=pace, position=shape, terminal=terminal, total=total)

    def _gaps_ahead(self) -> np.ndarray:
        """Each car's time gap to the car classified one place ahead — the traffic input.
        A leader gets the dirty-air threshold so it is never counted as being in traffic."""
        state = self._state
        gaps = np.full(self.n_cars, self.scenario.dirty_air_threshold_s)
        rank = state.positions()
        by_rank = np.argsort(rank, kind="stable")  # car index at each 0-based place
        for place in range(1, self.n_cars):
            car, ahead = by_rank[place], by_rank[place - 1]
            gaps[car] = state.cumulative_time_s[car] - state.cumulative_time_s[ahead]
        return gaps

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
        return self._state.track_status in (events.GREEN, events.VSC, events.RED)

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
        )

    def _coerce(self, action) -> tuple[int, int]:
        """Physics disposes: an action the mask forbids is snapped to a legal one, so a
        raw agent request can never execute something illegal (F-16)."""
        pit, mode = int(action[0]), int(action[1])
        mask = self._mask
        if not mask.mode[mode]:
            mode = _BALANCED
        if mask.pit[pit]:
            return pit, mode
        if mask.pit[0] and pit != 0:
            return 0, mode  # asked for an unavailable compound; stay out
        first = COMPOUNDS[int(self._state.first_compound[self._state.ego])]
        compounds = [k for k in np.flatnonzero(mask.pit) if k != 0]
        fresh = [k for k in compounds if COMPOUNDS[k - 1] != first]
        return int((fresh or compounds)[0]), mode

    def _observe(self) -> np.ndarray:
        ahead, behind, gap_ahead, gap_behind = self._neighbours()
        return observation.encode(
            self._state, self.scenario, gap_ahead_s=gap_ahead, gap_behind_s=gap_behind,
            ahead=ahead, behind=behind, pit_open=self._pit_open(),
        )

    def _info(self, terms: RewardTerms) -> dict:
        state = self._state
        ahead, behind, gap_ahead, gap_behind = self._neighbours()
        info = {
            "lap": state.lap,
            "position": int(state.positions()[state.ego]),
            "gap_ahead_s": gap_ahead,
            "gap_behind_s": gap_behind,
            "track_status": _STATUS_NAMES[state.track_status],
            "reward_terms": {
                "pace": terms.pace, "position": terms.position,
                "terminal": terms.terminal, "total": terms.total,
            },
            "energy": {
                "harvest_mj": float(state.last_harvest_mj[state.ego]),
                "deploy_mj": float(state.last_deploy_mj[state.ego]),
                "soc_mj": float(state.soc_mj[state.ego]),
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
            "dnf": dnf,
            "pit_laps": list(self._ego_pit_laps),
            "compounds": list(self._ego_pit_compounds),
            "derate_count": self._ego_derate_count,
            "energy_totals": {
                "harvest_mj": self._ego_harvest_total,
                "deploy_mj": self._ego_deploy_total,
            },
        }
