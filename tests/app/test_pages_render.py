"""Every page renders, with the honesty statements the spec requires still on them.

Streamlit's AppTest runs each page as it would run in the browser and hands back the
elements, so this is the closest thing to looking at the artefact that CI can do. It is
here because the F23 lesson was that a green suite is not a working page — a test suite
proves behaviour, and only running the thing proves it communicates.

The client is stubbed, so no database, API or model is needed.
"""

from pathlib import Path

import pyarrow
import pytest
from streamlit.testing.v1 import AppTest

# AppTest resolves relative paths against the calling file, not the repo root
REPO = Path(__file__).resolve().parents[2]

RUN_ID = 42
LAPS = 8
TIMEOUT_S = 60

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _frame(lap: int) -> dict:
    return {
        "lap": lap,
        "cars": [
            {"id": car, "s_track": 0.0, "position": ((car + lap) % 22) + 1,
             "compound": "MEDIUM" if lap < 5 else "HARD",
             "tyre_age": lap if lap < 5 else lap - 4,
             "gap_ahead_s": None if car == 0 else 1.2,
             "in_pit": car == 0 and lap == 5}
            for car in range(22)
        ],
        "agent": {"soc_mj": 2.4, "harvest_mj": 3.1, "deploy_mj": 3.0, "mode": 1,
                  "action": {"pit": 0, "mode": 1},
                  "reward_terms": {"pace": 0.04, "position": -0.2, "terminal": 0.0,
                                   "total": -0.16},
                  "mask_reasons": {}},
        "events": [{"kind": "sc", "car_id": None, "detail": None}] if lap == 3 else [],
    }


CARD = {
    "circuit": "chinese_grand_prix", "lap": 4, "track_status": "1",
    "state": {}, "masks": {"pit": [True] * 4 + [False] * 2, "mode": [True] * 4,
                           "reasons": {"4": "wet_only", "5": "wet_only"}},
    "action": {"pit": 0, "mode": 1}, "decision": "Lap 4 - stay out, run balanced",
    "probs": {"pit": [0.8, 0.1, 0.05, 0.05, 0.0, 0.0], "mode": [0.1, 0.7, 0.1, 0.1]},
    "drivers": {"pit": [["tyre_age_norm", 0.4], ["gap_ahead_norm", -0.2]],
                "mode": [["soc_frac", 0.3]]},
    "flip": ["the call flips if tyre_age_norm crossed 0.62"],
    "plain_language": "Tyre age was the strongest push toward this call.",
    "honesty": {"fidelity": {"pit": 0.9976, "mode": 0.9819},
                "model_version": "senna-ppo-test", "statement": "Attribution via a surrogate."},
}

RUN = {
    "run_id": RUN_ID, "status": "complete", "model_version": "senna-ppo-test",
    "env_config_hash": "abc123", "circuit_id": "chinese_grand_prix", "era": "2026",
    "seed": 55, "config": {"grid_position": 8},
    "summary": {"final_position": 3, "race_time_s": 5412.4, "dnf": False,
                "total_laps": LAPS, "nominal_lap_s": 95.0},
    "created_at": None, "started_at": None, "finished_at": None,
}


@pytest.fixture
def stub_client(monkeypatch):
    from app import client

    monkeypatch.setattr(client, "circuits", lambda: [
        {"id": "chinese_grand_prix", "race_laps": 56, "h_max_mj": 8.5,
         "coverage": {"deg_fit": True}},
    ])
    monkeypatch.setattr(client, "circuit", lambda slug: {
        "id": slug, "race_laps": 56, "h_max_mj": 8.5, "coverage": {"deg_fit": True},
        "compounds": {"2026": {"SOFT": "native", "MEDIUM": "native", "HARD": "native"}},
    })
    monkeypatch.setattr(client, "run", lambda run_id: RUN)
    monkeypatch.setattr(client, "frames", lambda run_id: [_frame(n) for n in range(1, LAPS + 1)])
    monkeypatch.setattr(client, "decisions", lambda run_id: [CARD])


def _page(path: str, **state) -> AppTest:
    at = AppTest.from_file(str(REPO / path), default_timeout=TIMEOUT_S)
    for key, value in state.items():
        at.session_state[key] = value
    at.run()
    assert not at.exception, at.exception[0].message if at.exception else ""
    return at


def _text(at: AppTest) -> str:
    """Everything the page put on screen, markdown and captions included."""
    parts = [element.value for element in at.markdown]
    parts += [element.value for element in at.caption]
    parts += [element.value for element in at.warning]
    parts += [element.value for element in at.info]
    return " ".join(str(part) for part in parts)


def test_the_race_page_reports_position_and_never_points(stub_client):
    # F25 retired the stock st.metric for the petrol stat tiles, so the claims are
    # pinned through the tiles' own markup — value cells, not loose substrings
    body = _text(_page("app/Home.py", run_id=RUN_ID))
    assert '>P8<' in body, "the grid tile lost its value"
    assert '>P3<' in body, "the finish tile lost its value"
    assert '>1<' in body, "the stop count is no longer asserted anywhere"
    # summary.points is the FIA table over points_divisor 2.5, so it would read as wrong
    assert "pts" not in body.lower()
    assert "points" not in body.lower()


def test_the_race_page_states_that_the_stints_were_read_back(stub_client):
    at = _page("app/Home.py", run_id=RUN_ID)
    body = _text(at)
    assert "no plan here that preceded the race" in body
    assert "service time is not shown" in body


def test_the_landing_page_states_the_simulator_is_not_calibrated_to_reality(stub_client):
    at = _page("app/Home.py")
    assert "sim-to-real" in _text(at)


def test_explainability_orders_reward_then_alternatives_then_shap(stub_client):
    at = _page("app/pages/1_Explainability.py", run_id=RUN_ID)
    body = _text(at)
    primary = body.index("Reward decomposition")
    secondary = body.index("Alternatives the policy weighed")
    assert primary < secondary, "reward decomposition is the primary explanation"
    # SHAP is behind an expander, which is the demotion made structural
    assert any("SHAP" in str(getattr(e, "label", "")) for e in at.expander)


def test_explainability_states_compliance_is_not_a_reward_term(stub_client):
    at = _page("app/pages/1_Explainability.py", run_id=RUN_ID)
    body = _text(at)
    assert "compliance comes from the action mask" in body
    assert "not a search over whole" in body


def test_explainability_says_shap_explains_a_surrogate(stub_client):
    at = _page("app/pages/1_Explainability.py", run_id=RUN_ID)
    assert "surrogate" in _text(at)


def test_explainability_reports_missing_explanations_rather_than_inventing_them(monkeypatch,
                                                                                stub_client):
    from app import client

    monkeypatch.setattr(client, "decisions", lambda run_id: [])
    at = _page("app/pages/1_Explainability.py", run_id=RUN_ID)
    # E-15: a retrained model explains only its own runs
    assert "No stored explanations" in _text(at)


def test_playback_starts_at_lap_one_and_shows_the_field(stub_client):
    # F25 retired the stock st.metric for the petrol stat tiles: pin through the body
    at = _page("app/pages/2_Playback.py", run_id=RUN_ID)
    body = _text(at)
    assert f"1 / {LAPS}" in body
    assert "Position" in body
    assert "nothing is re-simulated" in body


def test_a_page_without_a_run_asks_for_one_instead_of_failing(stub_client):
    at = _page("app/pages/2_Playback.py")
    assert "No race yet" in _text(at)


def test_every_page_carries_the_unofficial_project_footer(stub_client):
    from app.theme import DISCLAIMER

    for path, state in (("app/Home.py", {"run_id": RUN_ID}),
                        ("app/Home.py", {}),
                        ("app/pages/1_Explainability.py", {"run_id": RUN_ID}),
                        ("app/pages/2_Playback.py", {"run_id": RUN_ID})):
        assert DISCLAIMER in _text(_page(path, **state)), f"{path} lost the R-07 footer"


def _chart_rows(at: AppTest) -> list[dict]:
    """The data behind every altair chart on the page, as plain column dicts.

    AppTest has no accessor for charts, but the vega-lite proto carries the inlined
    datasets, so this is still an assertion on what the reader's chart actually shows."""
    tables = []
    for chart in at.get("vega_lite_chart"):
        for dataset in chart.proto.datasets:
            table = pyarrow.ipc.open_stream(dataset.data.data).read_all()
            tables.append(table.to_pydict())
    return tables


def test_the_race_page_leads_with_the_composed_headline(stub_client):
    from app.story import race_headline

    headline = race_headline([_frame(n) for n in range(1, LAPS + 1)],
                             RUN["summary"], RUN["config"]["grid_position"])
    at = _page("app/Home.py", run_id=RUN_ID)
    assert headline in _text(at), "the page's headline is not the composed one"


def test_the_race_page_marks_the_safety_car_on_the_moments_strip(stub_client):
    at = _page("app/Home.py", run_id=RUN_ID)
    # the stub race has exactly one event: an sc on lap 3
    strips = [
        table for table in _chart_rows(at)
        if 3 in table.get("lap", [])
        and any(str(value).lower() == "sc" or "safety" in str(value).lower()
                for column in table.values() for value in column)
    ]
    assert strips, "no chart data marks the lap-3 safety car"


def test_playback_draws_the_full_field_on_the_track_map(stub_client):
    from app.theme import TEAMS

    at = _page("app/pages/2_Playback.py", run_id=RUN_ID)
    maps = []
    for table in _chart_rows(at):
        if "x" not in table or "y" not in table:
            continue
        if any(len(column) != 22 for column in table.values()):
            continue
        maps.append(table)
    assert maps, "no chart with one x/y point per car"

    track = maps[0]
    values = {str(value) for column in track.values() for value in column}
    assert {"C01", "C22"} <= values, "car labels missing from the track map data"
    hexes = {value.lower() for value in values if value.startswith("#")}
    assert TEAMS[0][1].lower() in hexes, "the ego's team colour is not on the map"


def test_playback_states_the_track_map_is_illustrative(stub_client):
    body = _text(_page("app/pages/2_Playback.py", run_id=RUN_ID))
    assert "s_track" in body
    assert "illustrative" in body or "display-only" in body, \
        "the F11 display-only synthesis caveat left the screen"


def test_playback_colours_the_battery_gauge_from_the_soc_ramp(stub_client):
    from app.theme import SOC_RAMP

    at = _page("app/pages/2_Playback.py", run_id=RUN_ID)
    # spec only, never dataset values: a team hex in the track-map data must not be
    # able to stand in for the gauge (the review found exactly that vacuity), and
    # the gauge is the one chart whose spec carries the whole ramp as gradient stops
    specs = [chart.proto.spec.lower() for chart in at.get("vega_lite_chart")]
    assert any(all(step.lower() in spec for step in SOC_RAMP) for spec in specs), \
        "no chart's spec carries the full state-of-charge ramp"


def test_explainability_keeps_the_decision_line_on_screen(stub_client):
    at = _page("app/pages/1_Explainability.py", run_id=RUN_ID)
    assert CARD["decision"] in _text(at)
