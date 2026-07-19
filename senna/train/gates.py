"""Competence-gate decisions (spec 5.7, F-21) as pure functions of eval histories.

No gate takes a step budget: a ceiling hit is the loop's budget_stop, never a pass.
Every threshold arrives as a keyword from curriculum.yaml — a default here would be an
inline constant wearing a disguise. Stage A and B gates hold once triggered: training
stops on the first pass, so a later noisy eval must not flap an already-made decision.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True)
class StageAEval:
    step: int
    mean_return: float
    mean_race_time_s: float
    dnf_count: int


@dataclass(frozen=True)
class PairedRace:
    seed: int
    circuit: str
    agent_position: int
    agent_dnf: bool
    baseline_position: int
    baseline_dnf: bool


@dataclass(frozen=True)
class StageCEval:
    step: int
    mean_points: float


@dataclass(frozen=True)
class GateDecision:
    passed: bool
    reason: str
    values: dict


def plateaued(returns: Sequence[float], *, window: int, min_improvement: float,
              denominator_floor: float) -> tuple[bool, float]:
    """Best of the last `window` evals against the best before them. The naive
    consecutive-pairs reading passes a policy still gaining 0.9% every eval; over a
    window that compounds to ~2.7%, which this reading keeps training on."""
    best_before = max(returns[:-window])
    window_best = max(returns[-window:])
    improvement = (window_best - best_before) / max(abs(best_before), denominator_floor)
    return improvement < min_improvement, improvement


def stage_a_gate(history: Sequence[StageAEval], *, reference_time_s: float,
                 plateau_window: int, plateau_min_improvement: float,
                 time_tolerance: float, denominator_floor: float) -> GateDecision:
    """Plateau AND race time within tolerance of the solo reference, on the same eval.
    Scans prefixes so a pass holds even if later evals regress (trigger and hold)."""
    if len(history) < plateau_window + 1:
        return GateDecision(
            passed=False,
            reason=f"history too short: {len(history)} evals, plateau needs {plateau_window + 1}",
            values={"plateau_improvement": None, "time_delta_frac": None, "anomaly": None},
        )

    decision = None
    for end in range(plateau_window + 1, len(history) + 1):
        decision = _stage_a_decide(
            history[:end], reference_time_s=reference_time_s, plateau_window=plateau_window,
            plateau_min_improvement=plateau_min_improvement, time_tolerance=time_tolerance,
            denominator_floor=denominator_floor,
        )
        if decision.passed:
            return decision
    return decision


def _stage_a_decide(history, *, reference_time_s, plateau_window, plateau_min_improvement,
                    time_tolerance, denominator_floor) -> GateDecision:
    returns = [point.mean_return for point in history]
    flat, improvement = plateaued(
        returns, window=plateau_window, min_improvement=plateau_min_improvement,
        denominator_floor=denominator_floor,
    )
    latest = history[-1]
    delta_frac = (latest.mean_race_time_s - reference_time_s) / reference_time_s
    # one-sided: the reference is near-optimal, not provably optimal (greedy energy),
    # so a faster agent passes — but a beat beyond tolerance smells like a physics or
    # reference bug and is flagged for Saad, loudly
    anomaly = "beats_reference_beyond_tolerance" if delta_frac < -time_tolerance else None
    # dnf_count == 0 is a documented strengthening of 5.7: a DNF'd solo race corrupts
    # the mean-time bar, so competence requires a clean bank — it can only delay an
    # exit, never fake one, and the count is logged either way
    time_ok = delta_frac <= time_tolerance and latest.dnf_count == 0

    passed = flat and time_ok
    if passed:
        reason = (f"plateau ({improvement:.2%}) and time within {time_tolerance:.1%} "
                  f"at step {latest.step}")
    elif not flat:
        reason = f"still improving: {improvement:.2%} over the last {plateau_window} evals"
    else:
        reason = f"plateaued but off the time bar: {delta_frac:+.2%} vs the solo reference"
    return GateDecision(
        passed=passed,
        reason=reason,
        values={
            "step": latest.step,
            "plateau": flat,
            "plateau_improvement": improvement,
            "mean_race_time_s": latest.mean_race_time_s,
            "time_delta_frac": delta_frac,
            "dnf_count": latest.dnf_count,
            "anomaly": anomaly,
        },
    )


def pair_outcome(agent_position: int, agent_dnf: bool,
                 baseline_position: int, baseline_dnf: bool) -> tuple[bool, int]:
    """(agent finished ahead, position delta) for one paired race; positive delta means
    the agent ahead. A finisher beats any DNF, both-DNF is no evidence either way, and
    an equal classification counts against the agent — conservative by construction."""
    if agent_dnf and baseline_dnf:
        return False, 0
    delta = baseline_position - agent_position
    if agent_dnf:
        return False, delta
    if baseline_dnf:
        return True, delta
    return agent_position < baseline_position, delta


def stage_b_gate(pairs: Sequence[PairedRace], *, finish_ahead_min: float,
                 median_delta_min: float, n_required: int) -> GateDecision:
    if len(pairs) != n_required:
        raise ValueError(
            f"stage B gate needs exactly {n_required} pairs, got {len(pairs)} — a "
            "silently dropped seed would bias the finish-ahead rate"
        )
    outcomes = [
        pair_outcome(p.agent_position, p.agent_dnf, p.baseline_position, p.baseline_dnf)
        for p in pairs
    ]
    rate = sum(ahead for ahead, _ in outcomes) / n_required
    median_delta = float(median(delta for _, delta in outcomes))
    passed = rate >= finish_ahead_min and median_delta >= median_delta_min
    return GateDecision(
        passed=passed,
        reason=(
            f"finish-ahead {rate:.1%} vs {finish_ahead_min:.0%} floor, "
            f"median delta {median_delta:+.1f} vs {median_delta_min:+.1f}"
        ),
        values={
            "finish_ahead_rate": rate,
            "median_position_delta": median_delta,
            "n_pairs": n_required,
        },
    )


def stage_c_stop(history: Sequence[StageCEval], *, current_step: int,
                 stagnation_steps: int, min_improvement_points: float) -> GateDecision:
    """passed=True means STOP: the best validation points has not improved for
    stagnation_steps. An equal eval is not an improvement (strict best-so-far)."""
    best = history[0]
    for point in history[1:]:
        if point.mean_points > best.mean_points + min_improvement_points:
            best = point
    since = current_step - best.step
    stop = since >= stagnation_steps
    return GateDecision(
        passed=stop,
        reason=(
            f"{since:,} steps since the best validation eval "
            f"({best.mean_points:.2f} points at step {best.step:,})"
        ),
        values={"best_step": best.step, "best_points": best.mean_points,
                "steps_since_best": since},
    )


def select_checkpoint(history: Sequence[StageCEval]) -> StageCEval:
    """The 5.7 selection rule: highest validation points, ties to the earlier step —
    same measured quality, less opportunity to overfit the validation bank."""
    return max(history, key=lambda point: (point.mean_points, -point.step))
