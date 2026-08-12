"""Record the F16 golden traces — the byte-identity evidence for the engine extraction.

Run this at the commit BEFORE the extraction and commit the .npz output. Regenerating
it afterwards proves nothing: the fixture's whole job is to be a photograph of the race
as it ran when `F1RaceEnv.step()` still owned the tick, so that the extracted engine has
something independent to be equal to.

Recorded at 37c712d (docs: plan F16), 7 August 2026.

Since F18 the race is built from `pinned_configs/` rather than `configs/`, so the frozen
world the fixture photographs cannot drift when the fitted constants are refitted. That
keeps the fixture a statement about the engine tick, which is all it was ever evidence
for — a refit changes the physics, not whether the extraction preserved behaviour.

    python tests/env/fixtures/generate_f16_golden.py
"""

import pathlib

import numpy as np

from senna.env import F1RaceEnv

PINNED_CONFIGS = pathlib.Path(__file__).parent / "pinned_configs"

SEED = 512  # tests/env/conftest.py's module seed, so the fixture sits in the same stream
CIRCUITS = ("bahrain_grand_prix", "monaco_grand_prix")
FIELDS = (
    "cumulative_time_s",
    "positions",
    "soc_mj",
    "compound",
    "tyre_age",
    "fuel_kg",
    "retired",
)


def ego_action(lap: int) -> np.ndarray:
    """A fixed strategy with enough shape to exercise the paths that matter: two stops
    onto different compounds, and a mode that moves so the energy branch is not frozen
    at balanced for the whole race. Masks snap anything illegal, which is itself part of
    what the fixture pins down."""
    if lap == 14:
        return np.array([2, 1])  # pit to Medium
    if lap == 34:
        return np.array([3, 1])  # pit to Hard
    if lap < 8:
        return np.array([0, 0])  # conserve early, bank charge
    if 20 <= lap < 28:
        return np.array([0, 2])  # attack the middle stint
    return np.array([0, 1])


def record(circuit: str) -> dict:
    env = F1RaceEnv(circuit, "2026", configs_dir=PINNED_CONFIGS)
    env.reset(seed=SEED)
    state = env._state  # the fixture wants the whole field, not the ego observation
    frames = {name: [_snapshot(state, name)] for name in FIELDS}

    for lap in range(env.total_laps):
        _, _, terminated, _, _ = env.step(ego_action(lap))
        for name in FIELDS:
            frames[name].append(_snapshot(state, name))
        if terminated:
            break

    return {name: np.array(rows) for name, rows in frames.items()}


def _snapshot(state, name: str) -> np.ndarray:
    if name == "positions":
        return state.positions().copy()
    return np.asarray(getattr(state, name)).copy()


def main() -> None:
    here = pathlib.Path(__file__).parent
    for circuit in CIRCUITS:
        frames = record(circuit)
        path = here / f"F16_golden_{circuit}.npz"
        np.savez_compressed(path, **frames)
        laps, cars = frames["cumulative_time_s"].shape
        print(f"{path.name}: {laps} rows x {cars} cars")


if __name__ == "__main__":
    main()
