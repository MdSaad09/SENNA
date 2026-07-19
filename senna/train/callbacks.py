"""The training-loop callbacks: global schedules (5.6.1's linear decays driven by the
true global step, because SB3's own progress_remaining re-anchors at every learn()
call and would kink at each early gate exit), the per-term reward accounting behind
the 5.5.4 dominance ratio, throughput, and the gate evaluation that ends a stage the
moment its competence gate passes (R-12).
"""

import time

from stable_baselines3.common.callbacks import BaseCallback


class ScheduleCallback(BaseCallback):
    """lr start->end and ent_coef start->end, linear in num_timesteps over the summed
    stage ceilings. An early-gated run ends with lr above zero — documented cost of
    the one-schedule design (training.yaml schedules.horizon)."""

    def __init__(self, *, lr: tuple, ent: tuple, horizon_steps: int):
        super().__init__()
        self._lr0, self._lr1 = lr
        self._ent0, self._ent1 = ent
        self._horizon = horizon_steps

    def _on_rollout_start(self) -> None:
        frac = min(1.0, self.model.num_timesteps / self._horizon)
        lr = self._lr0 + frac * (self._lr1 - self._lr0)
        self.model.lr_schedule = lambda _progress: lr  # read by _update_learning_rate
        self.model.ent_coef = self._ent0 + frac * (self._ent1 - self._ent0)
        self.logger.record("train/ent_coef", self.model.ent_coef)

    def _on_step(self) -> bool:
        return True


class RewardTermsCallback(BaseCallback):
    """Per-episode sums of the reward decomposition from training rollouts, logged as
    means per rollout, plus the 5.5.4 dominance ratio: |terminal| over the summed
    magnitude of every other term, batch-level so points-zero episodes pull it down
    honestly. The keys come from the env's info["reward_terms"], so the F08 variant
    rewards (5.6.3) log their own decompositions without this callback caring which
    objective is in the saddle."""

    def __init__(self):
        super().__init__()
        self._open: list[dict] = []       # one running sum per worker
        self._window: list[dict] = []     # episodes closed since the last rollout end
        self._terminal_total = 0.0        # run-level, for the manifest and summary
        self._shaping_total = 0.0

    def _on_training_start(self) -> None:
        # a gate pass aborts learn() mid-episode: the previous stage's partial sums
        # and its aborted-rollout window must not leak into this stage's first means
        self._open = [{} for _ in range(self.training_env.num_envs)]
        self._window.clear()

    def _on_step(self) -> bool:
        for slot, info, done in zip(self._open, self.locals["infos"], self.locals["dones"],
                                    strict=True):
            for term, value in info["reward_terms"].items():
                if term != "total":
                    slot[term] = slot.get(term, 0.0) + value
            if done:
                self._window.append(dict(slot))
                self._terminal_total += abs(slot.get("terminal", 0.0))
                self._shaping_total += sum(abs(value) for term, value in slot.items()
                                           if term != "terminal")
                slot.clear()
        return True

    def _on_rollout_end(self) -> None:
        if not self._window:
            return
        n = len(self._window)
        for term in sorted({term for episode in self._window for term in episode}):
            mean = sum(episode.get(term, 0.0) for episode in self._window) / n
            self.logger.record(f"reward/{term}_ep_mean", mean)
        terminal = sum(abs(e.get("terminal", 0.0)) for e in self._window)
        shaping = sum(abs(value) for episode in self._window
                      for term, value in episode.items() if term != "terminal")
        # no ratio without a denominator: the terminal-only arm has shaping
        # identically zero, and |terminal|/epsilon would be noise dressed as telemetry
        if shaping > 0.0:
            self.logger.record("reward/dominance_ratio", terminal / shaping)
        self._window.clear()

    def run_dominance_ratio(self) -> float | None:
        """The whole run so far — 5.5.4 expects roughly 3 (terminal about 3x the
        maximum cumulative shaping). None when no shaping term ever fired (the
        terminal-only arm), and the manifest records that honestly."""
        if self._shaping_total == 0.0:
            return None
        return self._terminal_total / self._shaping_total


class ThroughputCallback(BaseCallback):
    def __init__(self):
        super().__init__()
        self._rollout_started = 0.0

    def _on_rollout_start(self) -> None:
        self._rollout_started = time.perf_counter()

    def _on_rollout_end(self) -> None:
        elapsed = time.perf_counter() - self._rollout_started
        stepped = self.model.n_steps * self.training_env.num_envs
        self.logger.record("perf/steps_s", stepped / max(elapsed, 1e-9))  # divide guard

    def _on_step(self) -> bool:
        return True


class GateEvalCallback(BaseCallback):
    """Every eval_every_steps: checkpoint last/, run the stage's gate evaluation, log
    the gate series, and return False on a pass so learn() ends the stage early —
    gates end stages, ceilings only cap them (F-21, R-12)."""

    def __init__(self, evaluate, *, every_steps: int, tracker, save_last, save_best=None):
        super().__init__()
        self._evaluate = evaluate
        self._every = every_steps
        self._next = None  # anchored to the stage's entry step at training start
        self._tracker = tracker
        self._save_last = save_last
        self._save_best = save_best
        self.decision = None
        self.last_eval_step = None

    def _on_training_start(self) -> None:
        # num_timesteps is global and cumulative across stages (reset_num_timesteps
        # False), so an absolute cadence would burst-evaluate every step at a stage
        # boundary until it caught up — anchor to wherever this stage begins
        self._next = self.model.num_timesteps + self._every

    @property
    def passed(self) -> bool:
        return self.decision is not None and self.decision.passed

    def run_eval(self) -> None:
        """One evaluation at the current step — also called by the loop at a ceiling
        so every stage exit is preceded by a real, logged gate evaluation."""
        step = self.num_timesteps
        self._save_last(step)
        self.decision = self._evaluate(step)
        self.last_eval_step = step
        series = {"gate/passed": float(self.decision.passed)}
        for key, value in self.decision.values.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                series[f"gate/{key}"] = float(value)
        self._tracker.log(series, step=step)
        if self._save_best is not None and self.decision.values.get("improved"):
            self._save_best(step)

    def _on_step(self) -> bool:
        if self.num_timesteps < self._next:
            return True
        self._next += self._every
        self.run_eval()
        return not self.decision.passed
