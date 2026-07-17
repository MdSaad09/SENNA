"""The three-term reward (spec 5.5.4). Nothing else is added — the whole point of
F-16 is that legality is masking, not a reward penalty, so the objective stays
exactly these three terms:

  pace shaping     scale-free per-lap gradient, an order below the terminal term
  position shaping potential-based, so it telescopes to zero on a closed loop (F-15)
  terminal points  the real 2026 table over 2.5, the objective the agent actually wants

Coefficients and their justification live in configs/env.yaml; this module is only
the arithmetic.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RewardTerms:
    pace: float
    position: float
    terminal: float
    total: float


def pace_shaping(lap_time_s: float, t_ref_s: float, s_ref_s: float, w_p: float) -> float:
    """w_p * (t_ref - lap_time) / s_ref — dividing by the circuit's clean-lap sigma
    makes the term scale-free across circuits (5.5.4)."""
    return w_p * (t_ref_s - lap_time_s) / s_ref_s


def position_potential(position: int, coef: float) -> float:
    """Phi(s) = -coef * position — a better place is a higher potential."""
    return -coef * position


def shaping_step(prev_position: int, position: int, coef: float, gamma: float) -> float:
    """F = gamma * Phi(s') - Phi(s). At gamma = 1 the per-step terms telescope, so any
    position path that returns to its start sums to exactly zero (F-15)."""
    return gamma * position_potential(position, coef) - position_potential(prev_position, coef)


def terminal_points(final_position: int, points_table: list, divisor: float, *, dnf: bool) -> float:
    """The 2026 points for a finishing place, scaled by the divisor so P1 = 10. A DNF
    pays zero rather than a negative — retirement already forfeits everything, and
    stacking a penalty double-counts the risk (documented choice, 5.5.4)."""
    if dnf or final_position > len(points_table):
        return 0.0
    return points_table[final_position - 1] / divisor
