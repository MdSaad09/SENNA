"""The frozen seed banks (configs/seeds.yaml), with the held-out test bank behind a
consumer check — E-06's discipline applied to seeds. F07 code never reads the test
bank; only the F14 evaluation may name itself as the consumer, and a test pins the
refusal."""

from dataclasses import dataclass

from senna import config


class SeedBankReservedError(RuntimeError):
    """The Stage C test bank is F14's — reading it during training is contamination."""


@dataclass(frozen=True)
class SeedBanks:
    stage_a: tuple
    stage_b: dict            # circuit -> seeds
    stage_b_overflow: tuple  # replacements for a DNF'd recording run, consumed in order
    stage_c_validation: dict


def load_banks(configs_dir=None) -> SeedBanks:
    """Every bank a training run may touch. The test bank is deliberately absent."""
    raw = config.load("seeds", configs_dir)["eval"]
    stage_b = {k: tuple(v) for k, v in raw["stage_b"].items() if k != "overflow"}
    return SeedBanks(
        stage_a=tuple(raw["stage_a"]["seeds"]),
        stage_b=stage_b,
        stage_b_overflow=tuple(raw["stage_b"]["overflow"]),
        stage_c_validation={k: tuple(v) for k, v in raw["stage_c"]["validation"].items()},
    )


def load_reserved_test_bank(configs_dir=None, *, consumer: str) -> dict:
    if consumer != "F14":
        raise SeedBankReservedError(
            f"the stage_c test bank is held out for the F14 evaluation, not '{consumer}' "
            "— training or tuning against it is seed contamination (E-06)"
        )
    raw = config.load("seeds", configs_dir)["eval"]["stage_c"]["test"]
    return {k: tuple(v) for k, v in raw.items()}
