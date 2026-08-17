"""The run-491 backstop: no compound the simulator serves is ever free (F24).

build_scenario is the last gate between physics_params.yaml and the F-16 mask
layer, so the guards live here: a zero-deg slick leaves available_compounds,
and a circuit left under min_dry_compounds refuses instead of serving an
F-20-unsatisfiable race.
"""

import shutil

import pytest
import yaml

from senna import config
from senna.env.scenario import build_scenario

CIRCUIT = "bahrain_grand_prix"  # the env suite's fixture circuit: three fitted 2026 slicks


@pytest.fixture
def configs_with_zeroed_slicks(tmp_path):
    """Copy the live configs and clip the named Bahrain 2026 slicks to a = 0.

    An edit on a copy, for the same reason driver_table.py copies: the repair
    scrubs the committed zeros, so the fixture plants its own rather than
    trusting whatever the last `make fit` left behind.
    """

    def plant(compounds):
        configs_dir = tmp_path / "configs"
        shutil.copytree(config.REPO_ROOT / "configs", configs_dir)
        params_path = configs_dir / "physics_params.yaml"
        params = yaml.safe_load(params_path.read_text())
        for compound in compounds:
            params["circuits"][CIRCUIT]["degradation"][2026][compound]["a"] = 0.0
        params_path.write_text(yaml.safe_dump(params))
        return configs_dir

    return plant


def test_zero_deg_slick_is_excluded_from_available_compounds(configs_with_zeroed_slicks):
    scenario = build_scenario(
        CIRCUIT, "2026", configs_dir=configs_with_zeroed_slicks(["SOFT"])
    )

    # a = 0 means the tyre never loses lap time; it may not reach the mask
    assert "SOFT" not in scenario.available_compounds
    assert set(scenario.available_compounds) == {"MEDIUM", "HARD"}


def test_fewer_than_two_dry_compounds_refuses_loudly(configs_with_zeroed_slicks):
    configs_dir = configs_with_zeroed_slicks(["SOFT", "MEDIUM"])

    # only HARD survives: below race.min_dry_compounds the F-20 two-compound
    # rule is unsatisfiable, so the circuit-era is refused by name
    with pytest.raises(ValueError, match=CIRCUIT):
        build_scenario(CIRCUIT, "2026", configs_dir=configs_dir)


def test_no_free_tyres_property():
    # run 491 as an invariant, over the committed configs: every circuit-era
    # build_scenario will actually serve has real wear on every slick it offers.
    # A loud refusal (ValueError here; KeyError is the loader's own refusal for
    # an unfitted block) is a legal outcome — serving a free tyre is not.
    params = config.load("physics_params")
    served_free = []
    for slug, circuit_params in params["circuits"].items():
        for era_int in (2024, 2026):
            if era_int not in circuit_params.get("joint_pace", {}):
                continue
            try:
                scenario = build_scenario(slug, str(era_int))
            except (ValueError, KeyError):
                continue
            served_free += [
                (slug, era_int, compound)
                for compound in scenario.available_compounds
                if scenario.deg_a[compound] <= 0.0
            ]

    assert served_free == []


def test_australia_2026_soft_wears_at_age_55():
    # run 491 by name: pit on lap 3, one set of softs 55 laps to P2. Either the
    # repair gave the Australian soft real wear or the guard pulled it from the
    # menu — a served zero is the bug.
    try:
        scenario = build_scenario("australian_grand_prix", "2026")
    except ValueError:
        return  # refused under min_dry_compounds: nothing free is served

    if "SOFT" in scenario.available_compounds:
        delta_s = scenario.deg_a["SOFT"] * scenario.t0_s * 55 ** scenario.deg_b["SOFT"]
        assert delta_s > 0.0
