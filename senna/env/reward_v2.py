"""v2's twelve-term reward, reconstructed for ablation 3 (5.6.3) from the master
spec's "v2 says" quotes — F-15 (the position asymmetry), F-16 (the -8 breach fine),
F-17 (the four coached bonuses), F-07 (the fastest-lap ghost) and R-02 (the removal
list this module deliberately resurrects). Pathologies included: the position pair
pays +0.2 for a lose-and-regain oscillation on purpose, because reproducing v2's
flaws is what makes the comparison honest. Coefficients live in configs/ablations.yaml
with per-term provenance; pace and terminal reuse v3's forms (senna/env/reward.py) so
the arm isolates what v2 added.
"""


def position_change(prev_position: int, position: int, *, gain: float,
                    loss: float) -> tuple[float, float]:
    """(gain term, loss term) for one lap. Asymmetric by v2's design — "+1.0 per
    position gained, -0.8 per position lost" — so a swap cycle nets +0.2, the F-15
    reward pump the potential-based v3 term telescopes away."""
    delta = prev_position - position  # positive means places gained
    if delta > 0:
        return gain * delta, 0.0
    if delta < 0:
        return 0.0, loss * -delta
    return 0.0, 0.0


def sc_pit_bonus(pitted: bool, sc_laps_active: int, *, bonus: float,
                 window_laps: int = 2) -> float:
    """The F-17 coached bonus: paid for boxing in the "first 2 laps of a safety car"
    (the window is part of the quote, hence the sourced default)."""
    return bonus if pitted and 1 <= sc_laps_active <= window_laps else 0.0


def ers_efficiency(deployed_mj: float, e_dep_mj: float, *, coef: float) -> float:
    """v2's "+0.1 x (MJ deployed / circuit-optimal MJ)". The circular denominator is
    read as the circuit's E_dep — the reconstruction ablations.yaml documents."""
    return coef * deployed_mj / e_dep_mj


def grip_stint_end(pitted: bool, grip_est: float, *, coef: float) -> float:
    """"+0.2 x grip remaining at stint end" — F-17's perverse incentive, kept: it
    pays for boxing early on barely-worn tyres."""
    return coef * grip_est if pitted else 0.0


def undercut_success(resolved_ahead: bool, *, bonus: float) -> float:
    """"+0.5 for a successful undercut/overcut". v2 never published the labelling
    rule; the env judges it undercut_window_laps after the stop (reconstructed)."""
    return bonus if resolved_ahead else 0.0


def ers_violation(derate_s: float, *, penalty: float) -> float:
    """v2 fined the breach it did not prevent: any lap the store derated the request
    pays the flat -8 (F-16 "v2 says"). Physics still clips — the fine is on top."""
    return penalty if derate_s > 0 else 0.0


def tyre_failure(failed: bool, *, penalty: float) -> float:
    """R-02's "tyre-failure -12", paid on the forced-pit event, not on termination —
    a tyre failure is +25 s and a stop in this simulator, never a DNF (5.5.5)."""
    return penalty if failed else 0.0


def fuel_exhausted(retired_by_fuel: bool, *, penalty: float) -> float:
    """R-02 lists a "fuel penalty" with no magnitude anywhere; -5.0 reconstructed,
    paid once on a fuel-exhaustion retirement."""
    return penalty if retired_by_fuel else 0.0


def fastest_lap_bonus(holds_fastest: bool, final_position: int, *, bonus: float,
                      points_places: int = 10) -> float:
    """"+1.0 if fastest lap claimed" inside the points — the rule the 2025 season
    abolished (F-07, R-01). Judged from race lap times at the flag, because the
    action that chased it was deleted with the ghost."""
    return bonus if holds_fastest and final_position <= points_places else 0.0
