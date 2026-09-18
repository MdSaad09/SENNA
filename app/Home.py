

import altair as alt
import pandas as pd
import streamlit as st

from app import client, theme
from app.story import race_headline, race_moments
from senna.serve.stints import pit_laps, stints_from_frames

EGO = 0  # the agent's car id, the F10 CarState contract
GRID_SLOTS = 22  # sourced — SimulationCreate bounds, 5.9.2 (ge=1, le=22): 22 cars, 11 teams
SOC_WINDOW_MJ = 4  # sourced — physics_2026.yaml energy_store.usable_capacity_mj (AR-04)
WEATHER = {"dry": "slick compounds", "mixed": "variable, reactive", "wet_risk": "wets likely"}

# the three archetypes the evaluation reports on, chosen because their 2026 degradation
# curves carry the circuit's own data rather than a cluster donor's (T5) — since F24
# the soft's shape comes from the repair ladder, which the archetype slice states
ARCHETYPES = {
    "chinese_grand_prix": "balanced",
    "australian_grand_prix": "flowing",
    "monaco_grand_prix": "street",
}

# stylised — host-country flags for the circuit picker, keyed by slug; a circuit
# missing here simply shows no flag, never a wrong one
FLAGS = {
    "abu_dhabi_grand_prix": "🇦🇪", "australian_grand_prix": "🇦🇺",
    "austrian_grand_prix": "🇦🇹", "azerbaijan_grand_prix": "🇦🇿",
    "bahrain_grand_prix": "🇧🇭", "belgian_grand_prix": "🇧🇪",
    "british_grand_prix": "🇬🇧", "canadian_grand_prix": "🇨🇦",
    "chinese_grand_prix": "🇨🇳", "dutch_grand_prix": "🇳🇱",
    "emilia_romagna_grand_prix": "🇮🇹", "french_grand_prix": "🇫🇷",
    "hungarian_grand_prix": "🇭🇺", "italian_grand_prix": "🇮🇹",
    "japanese_grand_prix": "🇯🇵", "las_vegas_grand_prix": "🇺🇸",
    "mexico_city_grand_prix": "🇲🇽", "miami_grand_prix": "🇺🇸",
    "monaco_grand_prix": "🇲🇨", "qatar_grand_prix": "🇶🇦",
    "saudi_arabian_grand_prix": "🇸🇦", "singapore_grand_prix": "🇸🇬",
    "spanish_grand_prix": "🇪🇸", "são_paulo_grand_prix": "🇧🇷",
    "united_states_grand_prix": "🇺🇸",
}

theme.page("Race")


def race_clock(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 3600}:{whole % 3600 // 60:02d}:{whole % 60:02d}"


def setup_panel() -> None:
    with st.sidebar:
        theme.eyebrow("Race configuration")
        library = client.circuits()
        if not library:
            st.error("The circuit library is empty — is the API running?")
            return

        runnable = [c for c in library if c["coverage"]["deg_fit"]]
        labels = {
            c["id"]: (f"{FLAGS.get(c['id'], '')} "
                      f"{c['id'].replace('_grand_prix', '').replace('_', ' ').title()}"
                      f"{'  ·  ' + ARCHETYPES[c['id']] if c['id'] in ARCHETYPES else ''}").strip()
            for c in runnable
        }
        default = next((i for i, c in enumerate(runnable) if c["id"] in ARCHETYPES), 0)
        slug = st.selectbox("Circuit", [c["id"] for c in runnable],
                            index=default, format_func=lambda s: labels[s])

        detail = client.circuit(slug) or {}
        chosen = next(c for c in runnable if c["id"] == slug)
        left, right = st.columns(2)
        left.metric("Race laps", chosen["race_laps"])
        right.metric("Harvest cap", f"{chosen['h_max_mj']} MJ")

        fits = (detail.get("compounds") or {}).get("2026", {})
        if fits:
            borrowed = [c for c, source in fits.items() if source == "transferred"]
            st.caption(
                "tyre model: " + ("all three compounds fitted here"
                                  if not borrowed else
                                  f"{', '.join(sorted(borrowed)).lower()} borrowed from "
                                  "another circuit (T5)")
            )

        st.divider()
        # boxed pickers: a chosen setting reads as a pressed key, not a form field
        weather = st.segmented_control(
            "Conditions", list(WEATHER), default="dry",
            format_func=lambda w: w.replace("_", " ")) or "dry"
        st.caption(WEATHER[weather])

        era = st.segmented_control("Era", ["2026", "2024"], default="2026") or "2026"
        band = st.segmented_control("Rival band", ["test", "train"],
                                    default="test") or "test"
        st.caption("test is the held-out band — the honest setting")

        grid = st.slider("Starting position", 1, GRID_SLOTS, 8)
        seed = st.text_input("Seed", placeholder="blank draws one, echoed back")

        st.divider()
        if st.button("Run race", type="primary", width='stretch'):
            if seed.strip() and not seed.strip().isdigit():
                st.error("Seed must be a whole number, or blank.")
                return
            body = {"circuit_id": slug, "grid_position": grid}
            if seed.strip():
                body["seed"] = int(seed)
            if era != "2026":
                body["era"] = era
            if weather != "dry":
                body["weather_profile"] = weather
            if band != "test":
                body["rival_band"] = band
            with st.spinner("Racing — the agent decides every lap, so this takes a moment"):
                try:
                    st.session_state["run_id"] = client.start_race(body)
                except client.ApiError as err:
                    st.error(str(err))
                    return
            st.rerun()


def stint_bar(stints) -> None:
    total = sum(s.laps for s in stints)
    rows = pd.DataFrame([
        {"stint": f"{i}", "compound": s.compound, "laps": s.laps,
         "start": s.start_lap, "end": s.end_lap}
        for i, s in enumerate(stints)
    ])
    chart = (
        alt.Chart(rows)
        .mark_bar(height=34)
        .encode(
            x=alt.X("sum(laps):Q", title=None, scale=alt.Scale(domain=[0, total]),
                    axis=alt.Axis(grid=False, labelColor=theme.FAINT, domainColor=theme.LINE)),
            color=alt.Color("compound:N", legend=None,
                            scale=alt.Scale(domain=list(theme.COMPOUND_COLOURS),
                                            range=list(theme.COMPOUND_COLOURS.values()))),
            order=alt.Order("stint:N"),
            tooltip=["compound", "laps", "start", "end"],
        )
        .properties(height=60)
        .configure_view(strokeWidth=0)
    )
    st.altair_chart(chart, width='stretch')


def moments_strip(frames: list[dict]) -> None:
    """The race's plot on one line: every stored track event plus the agent's stops,
    scannable before the story chart gives the detail."""
    moments = race_moments(frames)
    if not moments:
        st.caption("a clean race — no safety cars, no weather, and every event says so")
        return
    # token roles hold on the strip too: aqua is the agent's own action, alert is the
    # red flag, everything the track did is coast — ember stays an energy word (sheet)
    rows = pd.DataFrame([
        {"lap": m["lap"], "kind": m["kind"], "level": i % 2,
         "label": m["kind"].upper() if m["kind"] != "pit" else "PIT",
         "detail": m.get("detail") or "",
         "colour": theme.ACCENT if m["kind"] == "pit" else (
             theme.DANGER if m["kind"] == "red" else theme.COAST)}
        for i, m in enumerate(moments)
    ])
    last_lap = frames[-1]["lap"]
    base = alt.Chart(rows).encode(
        x=alt.X("lap:Q", title=None, scale=alt.Scale(domain=[1, last_lap]),
                axis=alt.Axis(grid=False, labelColor=theme.FAINT, domainColor=theme.LINE)),
    )
    # labels alternate two heights so clustered events (a pit under its own
    # safety car) stay legible instead of stacking into one word
    strip = alt.layer(
        base.mark_tick(thickness=2, size=18).encode(
            color=alt.Color("colour:N", scale=None),
            tooltip=["lap:Q", "kind:N", "detail:N"]),
        base.transform_filter(alt.datum.level == 0)
        .mark_text(dy=-16, fontSize=9, font="monospace").encode(
            text="label:N", color=alt.Color("colour:N", scale=None)),
        base.transform_filter(alt.datum.level == 1)
        .mark_text(dy=-28, fontSize=9, font="monospace").encode(
            text="label:N", color=alt.Color("colour:N", scale=None)),
    ).properties(height=64).configure_view(strokeWidth=0)
    st.altair_chart(strip, width='stretch')


def race_story(frames: list[dict], stints) -> None:
    """Position against lap for the whole field: where the agent came from, where the
    stops fell, and what the race did to both. Rival lines stay recessive grey —
    twenty-one team hues in one chart read as confusion, not identity (Saad's call,
    19 Aug); who-is-who lives on the track map and the tables, where it works."""
    rows = [
        {"lap": f["lap"], "car": theme.car_label(car["id"]),
         "position": car["position"], "agent": car["id"] == EGO}
        for f in frames for car in f["cars"]
    ]
    data = pd.DataFrame(rows)
    field = data[~data["agent"]]
    agent = data[data["agent"]]
    top = int(data["position"].max())

    axis_y = alt.Y("position:Q", title="position",
                   scale=alt.Scale(domain=[top, 1]),  # reversed: P1 belongs at the top
                   axis=alt.Axis(grid=True, gridColor=theme.CHART_GRID,
                                 labelColor=theme.FAINT, titleColor=theme.FAINT))
    axis_x = alt.X("lap:Q", title="lap",
                   axis=alt.Axis(grid=False, labelColor=theme.FAINT, titleColor=theme.FAINT))

    layers = [
        alt.Chart(field).mark_line(strokeWidth=1, opacity=0.45, color=theme.CHART_FIELD)
        .encode(x=axis_x, y=axis_y, detail="car:N",
                tooltip=["car:N", "lap:Q", "position:Q"]),
        alt.Chart(agent).mark_line(strokeWidth=2.5, color=theme.ACCENT)
        .encode(x=axis_x, y=axis_y,
                tooltip=[alt.Tooltip("lap:Q"), alt.Tooltip("position:Q", title="agent")]),
    ]
    stops = pit_laps(stints)
    if stops:
        marks = pd.DataFrame({"lap": stops})
        layers.append(
            alt.Chart(marks).mark_rule(color=theme.ACCENT, strokeDash=[3, 3], opacity=0.7)
            .encode(x="lap:Q")
        )
    st.altair_chart(
        alt.layer(*layers).properties(height=300).configure_view(strokeWidth=0),
        width='stretch',
    )


def result_panel(run_id: int) -> None:
    run = client.run(run_id)
    if run is None:
        st.error(f"No run {run_id}.")
        return
    if run["status"] != "complete":
        st.warning(f"Run {run_id} is {run['status']}.")
        return

    summary = run.get("summary") or {}
    frames = client.frames(run_id)
    if not frames:
        st.error(f"Run {run_id} finished but stored no frames — nothing honest to draw.")
        return
    stints = stints_from_frames(frames, EGO)
    grid = (run.get("config") or {}).get("grid_position")

    theme.eyebrow(f"Race strategy — as driven  ·  run {run_id}")
    st.markdown(f"### {FLAGS.get(run['circuit_id'], '')} "
                f"{run['circuit_id'].replace('_', ' ').title()}")
    theme.headline(race_headline(frames, summary, grid))

    # position only: summary.points is the FIA table divided by points_divisor 2.5
    # (configs/env.yaml), so a P2 finish serves 7.2 and printing it would read as wrong
    theme.stats([
        ("Grid", f"P{grid}" if grid else "—"),
        ("Finish", "DNF" if summary.get("dnf") else f"P{summary.get('final_position')}"),
        ("Stints", str(len(stints))),
        ("Stops", str(max(len(stints) - 1, 0))),
        ("Race laps", str(summary.get("total_laps", "—"))),
        ("Race time",
         race_clock(summary["race_time_s"]) if summary.get("race_time_s") else "—"),
    ])

    stint_bar(stints)
    moments_strip(frames)
    race_story(frames, stints)

    left, right = st.columns([3, 2])
    with left:
        theme.eyebrow("Pit stop schedule")
        stops = pit_laps(stints)
        if not stops:
            st.caption("no stops — the agent ran the whole race on one set")
        else:
            st.markdown(
                pd.DataFrame([
                    {"Stop": f"#{i + 1}", "From": stints[i].compound,
                     "To": stints[i + 1].compound, "Lap": lap}
                    for i, lap in enumerate(stops)
                ]).to_html(index=False, escape=False),
                unsafe_allow_html=True,
            )
            # deliberately four columns: engine.py computes pit_time_s, folds it into the
            # lap time and never puts it in info, so a service-time column would be made up
    with right:
        theme.eyebrow(f"Classification — lap {frames[-1]['lap']}")
        final = sorted(frames[-1]["cars"], key=lambda c: c["position"])
        st.dataframe(
            pd.DataFrame([
                {"Pos": c["position"], "Car": f"C{c['id'] + 1:02d}",
                 "Tyre": c["compound"], "Age": c["tyre_age"]}
                for c in final
            ]),
            hide_index=True, width='stretch', height=300,
        )

    theme.note(
        f"Stints are read back from run {run_id}'s stored frames — the agent chose them lap "
        "by lap in the simulator, and there is no plan here that preceded the race. Pit "
        "service time is not shown because the simulator does not serve it. Rival cars are "
        "scripted strategies fitted to historical data, not other learned agents."
    )
    theme.footer()


setup_panel()
run_id = st.session_state.get("run_id")
if run_id is None:
    theme.wordmark_hero("Formula 1 race strategy under the 2026 regulations")
    st.markdown(
        "A reinforcement-learning agent decides when to pit, which compound to fit and "
        "how to spend electrical energy — every lap, against 21 rival cars, under the "
        "2026 power-unit rules.\n\n"
        "**Configure a race in the sidebar and run it.** The agent races it in the "
        "simulator, then this page reports what it actually did."
    )
    theme.stats([
        ("The field", f"{GRID_SLOTS} <small>cars</small>"),
        ("Decisions", "2 <small>per lap</small>"),  # the two heads: pit, energy mode
        ("Energy window", f"{SOC_WINDOW_MJ} <small>MJ</small>"),
        ("Compliance", "masked <small>by construction</small>"),
    ])
    theme.eyebrow("The grid")
    theme.team_strip()
    st.caption("team identities are a display convention over car pairs — the "
               "simulator models seats, not constructors")
    theme.note(
        "Nothing here is a prediction about a real grand prix. The simulator is calibrated "
        "from 2022-25 telemetry and transformed to 2026 regulations; its sim-to-real "
        "agreement is measured and reported in the evaluation, and it does not meet the "
        "criterion set for it."
    )
    theme.footer()
else:
    result_panel(run_id)
