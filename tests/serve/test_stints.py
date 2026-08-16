"""The stint derivation, including the two cases a compound-change rule silently loses.

The property test is the point: a generator that only ever produces compound-changing
stops cannot fail a compound-change implementation, however many seeds it runs, and an
assertion that only checks "every boundary is a pit lap" is satisfied trivially by one.
Both directions are asserted, and the generator re-fits the same compound sometimes.
"""

import random

from senna.serve.stints import Stint, pit_laps, stints_from_frames

COMPOUNDS = ("SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET")


def frame(lap: int, compound: str, in_pit: bool, car_id: int = 0) -> dict:
    return {"lap": lap, "cars": [{"id": car_id, "compound": compound, "in_pit": in_pit}]}


def random_race(rng: random.Random) -> list[dict]:
    total = rng.randint(1, 60)
    compound = rng.choice(COMPOUNDS)
    frames = []
    for lap in range(1, total + 1):
        stops = lap > 1 and rng.random() < 0.15
        # a stop does NOT imply a compound change: engine.py writes the pit head's
        # compound whether or not it differs, and a failure-forced pit changes nothing
        if stops and rng.random() >= 0.15:
            compound = rng.choice([c for c in COMPOUNDS if c != compound])
        frames.append(frame(lap, compound, stops))
    return frames


def test_stints_partition_the_race_and_every_pit_opens_one():
    for seed in range(500):
        rng = random.Random(seed)
        frames = random_race(rng)
        total = len(frames)
        stints = stints_from_frames(frames)
        trace = f"seed {seed}"

        assert stints, trace
        assert stints[0].start_lap == 1, trace
        assert stints[-1].end_lap == total, trace
        assert sum(s.laps for s in stints) == total, trace

        for earlier, later in zip(stints, stints[1:], strict=False):
            assert later.start_lap == earlier.end_lap + 1, trace

        boundaries = {s.start_lap for s in stints[1:]}
        # the direction that bites: a compound-change rule passes the converse trivially
        for entry in frames[1:]:
            if entry["cars"][0]["in_pit"]:
                assert entry["lap"] in boundaries, f"{trace}: pit on lap {entry['lap']}"


def test_a_two_stop_race_reads_as_three_stints():
    frames = [
        frame(1, "SOFT", False), frame(2, "SOFT", False),
        frame(3, "MEDIUM", True), frame(4, "MEDIUM", False), frame(5, "MEDIUM", False),
        frame(6, "HARD", True), frame(7, "HARD", False),
    ]
    assert stints_from_frames(frames) == [
        Stint("SOFT", 1, 2), Stint("MEDIUM", 3, 5), Stint("HARD", 6, 7),
    ]
    assert pit_laps(stints_from_frames(frames)) == [3, 6]


def test_a_stop_onto_the_same_compound_still_counts():
    frames = [frame(1, "HARD", False), frame(2, "HARD", False),
              frame(3, "HARD", True), frame(4, "HARD", False)]
    assert stints_from_frames(frames) == [Stint("HARD", 1, 2), Stint("HARD", 3, 4)]
    assert pit_laps(stints_from_frames(frames)) == [3]


def test_a_failure_forced_pit_opens_a_stint_though_nothing_changed():
    frames = [frame(1, "SOFT", False), frame(2, "SOFT", True), frame(3, "SOFT", False)]
    assert len(stints_from_frames(frames)) == 2


def test_a_race_that_never_pits_is_one_stint():
    frames = [frame(lap, "HARD", False) for lap in (1, 2, 3)]
    assert len(stints_from_frames(frames)) == 1
    assert pit_laps(stints_from_frames(frames)) == []


def test_no_frames_means_no_stints():
    assert stints_from_frames([]) == []


def test_one_car_ignores_the_rest_of_the_field():
    frames = [
        {"lap": 1, "cars": [{"id": 0, "compound": "SOFT", "in_pit": False},
                            {"id": 1, "compound": "HARD", "in_pit": False}]},
        {"lap": 2, "cars": [{"id": 0, "compound": "HARD", "in_pit": True},
                            {"id": 1, "compound": "HARD", "in_pit": False}]},
    ]
    assert len(stints_from_frames(frames, car_id=0)) == 2
    assert len(stints_from_frames(frames, car_id=1)) == 1
