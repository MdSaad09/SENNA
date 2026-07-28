"""Neutralisation windows and the spliced replay that M5 and M6 branch alternatives from.

The timing rule is the whole subtlety. The action for lap L is chosen against the mask
built at the end of lap L-1, so a safety car deployed on lap w1 is first visible to the
decision taken for lap w1+1. A stop that lands on the onset lap was called before the car
could know, and grading it as a safety-car decision would credit the agent with foresight
it did not have. Hence the published denominator: a window is a decision opportunity only
when it offers at least one informed lap.

Branching is well defined because the twin freezes everything the ego does not control —
status, weather, failures, rival pits, service times and lap noise all come from the trace.
The corollary is worth stating in the write-up rather than hiding: rivals do not react to
a counterfactual ego stop, the same assumption the oracle publishes as its second.
"""

from dataclasses import dataclass

import numpy as np

from senna.env import events

_WINDOW_STATUS = {events.VSC: "vsc", events.SC: "sc"}


@dataclass(frozen=True)
class Window:
    status: str
    first_lap: int  # 1-based onset
    last_lap: int

    def decision_laps(self, last_completed_lap: int) -> list:
        """The laps inside this window whose action was chosen knowing about it."""
        return list(range(self.first_lap + 1, min(self.last_lap, last_completed_lap) + 1))


def neutralisation_windows(trace, *, last_lap: int) -> list:
    """Maximal runs of one neutralised status. A red flag is never a window and breaks the
    runs on either side of it: under red the tyre change is free, which is a different
    mechanism from a discounted pit loss and would pollute the metric (E-04)."""
    windows, start, current = [], None, None
    for index, raw in enumerate(trace.status):
        status = _WINDOW_STATUS.get(int(raw))
        if status != current:
            if current is not None:
                windows.append(Window(status=current, first_lap=start, last_lap=index))
            start, current = index + 1, status
    if current is not None:
        windows.append(Window(status=current, first_lap=start, last_lap=len(trace.status)))

    # a window offering no informed decision lap is not an opportunity the agent declined
    return [window for window in windows if window.decision_laps(last_lap)]


class SplicedPolicy:
    """Replay a fixed prefix of actions, then hand the race back to a live policy.

    ScriptedActions holds station once its script runs out, which is right for driving a
    twin to a branch point and wrong for everything after one: an afterstate variant has to
    keep racing to the flag, and a frozen tail would grade every alternative against a car
    that stopped strategising. The continuation is the agent's own policy on purpose —
    re-optimising the tail with full knowledge would grade the call by a perfect future the
    agent never had, which is M3's question, not M5's.
    """

    def __init__(self, prefix_actions, tail_policy):
        self._prefix = [np.asarray(action) for action in prefix_actions]
        self._tail = tail_policy
        self._index = 0

    def reset(self, obs, info, *, rng=None) -> None:
        self._index = 0
        self._tail.reset(obs, info, rng=rng)

    def act(self, obs, info, mask) -> np.ndarray:
        if self._index < len(self._prefix):
            action = self._prefix[self._index]
            self._index += 1
            return action
        return np.asarray(self._tail.act(obs, info, mask))

    @property
    def snapped(self) -> int:
        return int(getattr(self._tail, "snapped", 0))
