import pytest
import yaml

from senna.physics.fits.params_writer import (
    IncompleteParamsError,
    render_params,
    validate_complete,
    validate_origins,
)

GENERATED_AT = "2026-07-15T00:00:00Z"


def _params():
    # leaves are (value, origin) pairs; the origin becomes the line comment
    return {
        "globals": {"k_m_pooled_s_per_kg": (0.031, "fitted: fit_joint_pace.ipynb")},
        "monza": {
            "pit_loss": {
                "mean_s": (21.4, "fitted: fit_pit_loss.ipynb"),
                "n_stops": (48, "fitted: fit_pit_loss.ipynb"),
            },
            "hazards": {"sc_p_per_race": (0.3, "fitted: fit_hazards.ipynb")},
        },
        "spa": {
            "pit_loss": {
                "mean_s": (18.9, "fitted: fit_pit_loss.ipynb"),
                "n_stops": (30, "fitted: fit_pit_loss.ipynb"),
            },
        },
    }


def _reversed_insertion(mapping):
    if not isinstance(mapping, dict):
        return mapping
    return {key: _reversed_insertion(mapping[key]) for key in reversed(list(mapping))}


def test_rendered_yaml_round_trips_through_safe_load():
    loaded = yaml.safe_load(render_params(_params(), generated_at=GENERATED_AT))

    assert loaded["globals"]["k_m_pooled_s_per_kg"] == 0.031
    assert loaded["monza"]["pit_loss"]["mean_s"] == 21.4
    assert loaded["monza"]["pit_loss"]["n_stops"] == 48
    assert loaded["spa"]["pit_loss"]["mean_s"] == 18.9
    # loads back as the string it was given, not a parsed timestamp
    assert loaded["generated_at"] == GENERATED_AT


def test_every_value_line_carries_an_origin_comment():
    rendered = render_params(_params(), generated_at=GENERATED_AT)

    def is_value_line(line):
        before_comment = line.split("#", 1)[0].strip()
        if not before_comment or ":" not in before_comment:
            return False
        return before_comment.split(":", 1)[1].strip() != ""

    value_lines = [line for line in rendered.splitlines() if is_value_line(line)]
    assert value_lines  # the check must actually bite

    # the interpretability contract: no number without a named origin
    for line in value_lines:
        assert "#" in line, f"uncommented value line: {line!r}"
        assert any(origin in line for origin in ("sourced", "fitted", "stylised")), (
            f"no origin on: {line!r}"
        )


def test_scientific_notation_floats_load_back_as_floats():
    # YAML 1.1 wants a dot in scientific notation: repr(7e-06) == "7e-06"
    # loads back as a *string* under safe_load, silently poisoning every
    # downstream mean over degradation coefficients
    params = {"monza": {"degradation": {"a": (7e-06, "fitted: fit_degradation.ipynb")}}}

    loaded = yaml.safe_load(render_params(params, generated_at=GENERATED_AT))

    assert isinstance(loaded["monza"]["degradation"]["a"], float)
    assert loaded["monza"]["degradation"]["a"] == pytest.approx(7e-06)


def test_two_renders_are_byte_identical_regardless_of_insertion_order():
    forward = render_params(_params(), generated_at=GENERATED_AT)
    backward = render_params(_reversed_insertion(_params()), generated_at=GENERATED_AT)

    # `git diff` after a make fit rerun must be empty, whatever order the
    # orchestrator assembled the dict in
    assert forward == backward
    assert render_params(_params(), generated_at=GENERATED_AT) == forward


def test_validate_complete_raises_naming_every_null_key():
    validate_complete(_params())  # complete params pass silently

    params = _params()
    params["monza"]["pit_loss"]["mean_s"] = (None, "fitted: fit_pit_loss.ipynb")
    params["spa"]["pit_loss"]["n_stops"] = (None, "fitted: fit_pit_loss.ipynb")

    with pytest.raises(IncompleteParamsError) as excinfo:
        validate_complete(params)

    # F05 debugging starts from this message -- it must name the dotted paths
    assert "monza.pit_loss.mean_s" in str(excinfo.value)
    assert "spa.pit_loss.n_stops" in str(excinfo.value)


def test_params_refuse_non_finite_values():
    params = _params()
    params["monza"]["pit_loss"]["mean_s"] = (float("nan"), "fitted: fit_pit_loss.ipynb")
    params["spa"]["pit_loss"]["mean_s"] = (float("inf"), "fitted: fit_pit_loss.ipynb")
    params["monza"]["hazards"]["sc_p_per_race"] = (float("-inf"), "fitted: fit_hazards.ipynb")

    # a NaN is not None, so the null check waves it through and the emitter writes
    # the bare literal `nan` into physics_params.yaml -- which safe_load hands back
    # to F05 as a float that silently poisons every mean taken over it. The joint
    # fit produced exactly this shape of value on the 2022 seasons (E-09).
    with pytest.raises(IncompleteParamsError) as excinfo:
        validate_complete(params)

    assert "monza.pit_loss.mean_s" in str(excinfo.value)
    assert "spa.pit_loss.mean_s" in str(excinfo.value)
    assert "monza.hazards.sc_p_per_race" in str(excinfo.value)


def test_the_finite_gate_is_read_from_config_not_assumed():
    params = _params()
    params["monza"]["pit_loss"]["mean_s"] = (float("nan"), "fitted: fit_pit_loss.ipynb")

    # gates.require_finite_params off is the pre-F18 writer, and the only reason it can
    # be turned off is to demonstrate what that writer let through. If this passes with
    # the flag ignored, the constant in configs/fits.yaml is decoration.
    validate_complete(params, require_finite=False)

    # a null is not a gated case -- an unfitted constant is refused either way
    params["spa"]["pit_loss"]["mean_s"] = (None, "fitted: fit_pit_loss.ipynb")
    with pytest.raises(IncompleteParamsError) as excinfo:
        validate_complete(params, require_finite=False)
    assert "spa.pit_loss.mean_s" in str(excinfo.value)
    assert "monza.pit_loss.mean_s" not in str(excinfo.value)


def test_params_refuse_an_untagged_origin():
    # the four tags are the whole vocabulary, in the grammars the shipped file
    # actually uses: "fitted: <notebook>", "sourced <where> — why", "stylised — why"
    validate_origins(
        {
            "globals": {
                "race_fuel_kg": (70.0, "sourced AR-10 — grade C until Saad verifies it"),
                "k_m_pooled_s_per_kg": (0.031, "fitted: notebooks/fit_joint_pace.ipynb"),
                "sc_burn_factor": (0.6, "stylised — SC laps burn less; the ratio is a choice"),
                "require_full_season_coverage": (True, "operational — a gate, not a tunable"),
            }
        }
    )

    params = _params()
    params["monza"]["pit_loss"]["mean_s"] = (21.4, "")
    params["spa"]["pit_loss"]["n_stops"] = (30, "measured off a stopwatch")
    # "refitted" is not a tag; a substring search over the four would let it past,
    # and the interpretability contract is that the tag opens the comment
    params["monza"]["hazards"]["sc_p_per_race"] = (0.3, "refitted: fit_hazards.ipynb")

    with pytest.raises(IncompleteParamsError) as excinfo:
        validate_origins(params)

    assert "monza.pit_loss.mean_s" in str(excinfo.value)
    assert "spa.pit_loss.n_stops" in str(excinfo.value)
    assert "monza.hazards.sc_p_per_race" in str(excinfo.value)
