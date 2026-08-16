"""What the agent did with its tyres, read back out of a finished race.

There is no served stint list, so it is derived from the stored frames — but from
`in_pit`, not from the compound changing. The two are not the same signal, and the
difference loses real stops:

  - a stop onto the compound already fitted. `changed = pit != STAY_OUT` is true and
    pit_count increments, but `np.where(changed, pit, compound)` writes the value the
    car already held (senna/env/engine.py). Nothing in masks.py forbids that call.
  - a forced pit after a tyre failure: `changed` is false, `failed` is true, so the
    compound is untouched and pit_count still increments.

`in_pit` is `pit_count > prev.pit_count` (senna/serve/frames.py) and catches both.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Stint:
    compound: str
    start_lap: int
    end_lap: int

    @property
    def laps(self) -> int:
        return self.end_lap - self.start_lap + 1


def stints_from_frames(frames: list[dict], car_id: int = 0) -> list[Stint]:
    """One Stint per run of laps between stops, in lap order."""
    stints: list[Stint] = []
    for frame in frames:
        car = next((c for c in frame["cars"] if c["id"] == car_id), None)
        if car is None:
            continue
        lap = int(frame["lap"])
        # a compound change without in_pit means the two served signals disagree; split
        # anyway, because a stint drawn as one compound over two is wrong either way
        boundary = not stints or car["in_pit"] or stints[-1].compound != car["compound"]
        if boundary:
            stints.append(Stint(car["compound"], lap, lap))
        else:
            stints[-1] = Stint(stints[-1].compound, stints[-1].start_lap, lap)
    return stints


def pit_laps(stints: list[Stint]) -> list[int]:
    """The lap each stop happened on: every stint's first lap except the one the car
    started the race on."""
    return [stint.start_lap for stint in stints[1:]]
