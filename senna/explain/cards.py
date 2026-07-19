"""The decision card (A-03, 5.8.3): the recruiter-readable artifact, one JSON per
decision, shaped for the agent_decisions JSONB (5.3.5). The card never leaves numpy
types in the payload, and it refuses to explain a ghost — a surrogate fitted to one
checkpoint stays silent about every other (E-15 pairing).
"""

import numpy as np

from senna.env.masks import ATTACK_MODE
from senna.explain.features import FEATURE_NAMES

_PIT_CALLS = ("stay out", "pit for Soft", "pit for Medium", "pit for Hard",
              "pit for Intermediate", "pit for Wet")
_MODE_CALLS = ("conserve energy", "run balanced", "attack", "defend")


class VersionMismatchError(RuntimeError):
    """The surrogate was fitted to a different checkpoint — never explain a ghost."""


def build_card(record, *, pit_drivers, mode_drivers, flip_lines, fidelity,
               model_version: str, surrogate_version: str) -> dict:
    if surrogate_version != model_version:
        raise VersionMismatchError(
            f"surrogate fitted to {surrogate_version} cannot explain "
            f"{model_version} — re-run make explain against the current triplet (E-15)"
        )

    pit_mask, mode_mask = record.mask[:6], record.mask[6:]
    return {
        "circuit": record.circuit,
        "lap": record.lap,
        "track_status": record.track_status,
        "state": {name: float(v) for name, v in zip(FEATURE_NAMES, record.obs, strict=True)},
        "masks": {
            "pit": [bool(b) for b in pit_mask],
            "mode": [bool(b) for b in mode_mask],
            "reasons": dict(record.reasons),
        },
        "action": {"pit": int(record.pit_action), "mode": int(record.mode_action)},
        "probs": {
            "pit": [float(p) for p in record.pit_probs_masked],
            "mode": [float(p) for p in record.mode_probs_masked],
        },
        "drivers": {
            "pit": [[name, float(v)] for name, v in pit_drivers],
            "mode": [[name, float(v)] for name, v in mode_drivers],
        },
        "flip": list(flip_lines),
        "plain_language": _plain_language(record, pit_drivers),
        "honesty": {
            "fidelity": {head: float(v) for head, v in fidelity.items()},
            "model_version": model_version,
            "statement": (
                f"Attribution of the trained policy via a "
                f"{fidelity['pit']:.0%}-faithful surrogate; not a causal claim."
            ),
        },
    }


def _plain_language(record, pit_drivers) -> str:
    """One honest sentence: the call, its confidence, and the input that moved it
    most. Deterministic template, no generation — the card must never say more than
    the attribution supports."""
    call = _PIT_CALLS[record.pit_action]
    if record.mode_action == ATTACK_MODE:
        call += ", attacking on energy"
    confidence = float(np.max(record.pit_probs_masked))
    top_name, top_value = pit_drivers[0]
    direction = "pushed toward" if top_value >= 0 else "pushed against"
    return (f"Lap {record.lap}: {call} (probability {confidence:.2f}); "
            f"{top_name.replace('_', ' ')} {direction} the call hardest.")
