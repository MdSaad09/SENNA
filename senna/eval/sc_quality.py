"""M5 — SC/VSC decision quality against the ex-post afterstate optimum (5.12, E-03).

For each neutralisation window the agent raced through, the harness re-rolls the same race
with the window's decision replaced: once holding station, and once for every lap and legal
compound it could have boxed on. The best of those against the stay-out time is the ex-post
answer, and the agent's own choice is scored against it.

Two definitions carry into the report because the number is meaningless without them.

The denominator: one decision opportunity is one window offering at least one informed
decision lap. A stop on the onset lap was chosen against a mask built before the safety car
existed, so it is neither a call nor a miss — it is not a decision about this window at all.

The alternative's continuation: variants replay the agent's realised actions after the
window, changing only what happens inside it. This is the same coordinate-wise information
set M6 uses, and it keeps the label a property of the race rather than of the policy. The
cost, stated rather than hidden: a stop whose value would only show up under a different
follow-up plan is priced conservatively here.

Precision and recall are reported together and per status type. Recall alone is the
gameable half — an always-pit call sheet never misses an opportunity — which is exactly
what 5.12 replaced v2's single "SC exploitation" number to avoid.
"""

from senna.strategy.oracle import legal_codes_at
from senna.strategy.policy import ScriptedActions
from senna.strategy.rollout import run_episode

_STATUS_KEYS = ("sc", "vsc")
_VARIANT_SEED = 0  # twin rolls are deterministic; this only anchors the unused policy stream


def window_verdict(window, *, race, scenario, env, cfg) -> dict:
    """Label one window by re-rolling its alternatives on the frozen trace."""
    actions = [action.copy() for action in race.actions]
    decision_laps = window.decision_laps(len(actions))
    verdict = {
        "status": window.status,
        "first_lap": window.first_lap,
        "last_lap": window.last_lap,
        "agent_called_pit": any(lap in decision_laps for lap in race.pit_laps),
        "excluded": None,
    }
    if not decision_laps:
        return {**verdict, "label": "immaterial", "best_pit_time_s": None,
                "stay_time_s": None, "margin_s": None, "excluded": "no_informed_lap"}

    stay_time_s = _roll(env, actions, decision_laps, pit_lap=None, compound=None)

    best_pit_time_s = None
    for lap in decision_laps:
        for code in legal_codes_at(scenario, env.twin, lap):
            rolled = _roll(env, actions, decision_laps, pit_lap=lap, compound=code)
            if best_pit_time_s is None or rolled < best_pit_time_s:
                best_pit_time_s = rolled

    if best_pit_time_s is None:  # no compound was legal anywhere in the window
        return {**verdict, "label": "immaterial", "best_pit_time_s": None,
                "stay_time_s": stay_time_s, "margin_s": None, "excluded": "no_legal_stop"}

    margin_s = stay_time_s - best_pit_time_s
    if margin_s > cfg["label_margin_s"]:
        label = "pit"
    elif margin_s < -cfg["label_margin_s"]:
        label = "stay"
    else:
        label = "immaterial"
    return {**verdict, "label": label, "best_pit_time_s": best_pit_time_s,
            "stay_time_s": stay_time_s, "margin_s": margin_s,
            "excluded": "immaterial" if label == "immaterial" else None}


def _roll(env, actions, decision_laps, *, pit_lap, compound) -> float:
    """One variant: the realised action list with the window's decisions rewritten. The
    twin is sticky on the env, so run_episode's own reset replays the same race; the seed
    only picks the policy stream, which a scripted policy never draws from."""
    variant = [action.copy() for action in actions]
    for lap in decision_laps:
        index = lap - 1
        if index < len(variant):
            variant[index][0] = 0  # hold station through the window by default
    if pit_lap is not None:
        variant[pit_lap - 1][0] = compound + 1  # pit head: 0 stay, else compound code + 1

    return run_episode(env, ScriptedActions(variant), seed=_VARIANT_SEED).race_time_s


def sc_decision_quality(verdicts, *, cfg) -> dict:
    """Precision and recall per status type, with every excluded window counted by reason.
    Pooling SC and VSC would hide the case 5.12 cares about: an agent that answers the
    cheap opportunity well and the expensive one badly (E-03)."""
    excluded: dict[str, int] = {}
    for verdict in verdicts:
        if verdict["excluded"]:
            excluded[verdict["excluded"]] = excluded.get(verdict["excluded"], 0) + 1

    scored = {}
    for status in _STATUS_KEYS:
        rows = [v for v in verdicts if v["status"] == status and not v["excluded"]]
        tp = sum(1 for v in rows if v["label"] == "pit" and v["agent_called_pit"])
        fp = sum(1 for v in rows if v["label"] == "stay" and v["agent_called_pit"])
        fn = sum(1 for v in rows if v["label"] == "pit" and not v["agent_called_pit"])
        tn = sum(1 for v in rows if v["label"] == "stay" and not v["agent_called_pit"])
        scored[status] = {
            "precision": tp / (tp + fp) if tp + fp else float("nan"),
            "recall": tp / (tp + fn) if tp + fn else float("nan"),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "n_windows": len(rows),
        }

    targets = {"precision": cfg["precision_target"], "recall": cfg["recall_target"]}
    met = all(
        scored[status][name] >= target
        for status in _STATUS_KEYS
        for name, target in targets.items()
        if scored[status]["n_windows"]
    )
    return {**scored, "excluded": excluded, "targets": targets, "met": bool(met)}
