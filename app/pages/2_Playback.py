"""The race, lap by lap.

One stored frame per lap, 22 cars — and since F25 they are ON a track: s_track is
the serve layer's display-only synthesis of lap fraction (F11 labels it
illustrative), drawn on a stylised loop with team colours carrying identity. The
canvas glow reads the car's energy state per the gradient sheet: aqua while the
lap banked more than it spent, ember when deployment won.

Scrubbing and playing are reads of stored frames, never re-simulations (E-16). The
whole race already finished before this page opened.
"""

import time

import altair as alt
import pandas as pd
import streamlit as st

from app import theme, trackmap
from app.client import frames as fetch_frames
from senna.serve.stints import stints_from_frames

EGO = 0
STEP_SECONDS = 0.35  # operational — a readable lap rate; the sim's own pace is irrelevant here
SOC_CAPACITY_MJ = 4.0  # sourced — physics_2026.yaml energy_store.usable_capacity_mj;
                       # the gauge's full scale, the 4 MJ window the SOC lives in

theme.page("Playback")
theme.eyebrow("Playback")
st.title("The race, lap by lap")

run_id = theme.require_run()
if run_id is None:
    theme.footer()
    st.stop()

frames = fetch_frames(run_id)
if not frames:
    st.error(f"Run {run_id} stored no frames.")
    theme.footer()
    st.stop()

last_lap = frames[-1]["lap"]
st.session_state.setdefault("playhead", 1)
st.session_state.setdefault("playing", False)

controls = st.columns([1, 1, 6])
if controls[0].button("Play" if not st.session_state["playing"] else "Pause",
                      width='stretch'):
    st.session_state["playing"] = not st.session_state["playing"]
    st.rerun()
if controls[1].button("Restart", width='stretch'):
    st.session_state.update(playhead=1, playing=False)
    st.rerun()

playhead = controls[2].slider("Lap", 1, last_lap, st.session_state["playhead"],
                              label_visibility="collapsed")
if playhead != st.session_state["playhead"]:
    st.session_state.update(playhead=playhead, playing=False)

lap = st.session_state["playhead"]
frame = next(f for f in frames if f["lap"] == lap)
agent = next(c for c in frame["cars"] if c["id"] == EGO)
stints = stints_from_frames([f for f in frames if f["lap"] <= lap], EGO)
energy = frame["agent"]

# the sheet's ambient rule: one glow, keyed to what this lap's energy actually did
theme.ambient("harvesting" if energy["harvest_mj"] >= energy["deploy_mj"] else "deploying")

theme.stats([
    ("Lap", f"{lap} / {last_lap}"),
    ("Position", f"P{agent['position']}"),
    ("Tyre", f"{agent['compound']} · {agent['tyre_age']}L"),
    ("Battery", f"{energy['soc_mj']:.2f} <small>MJ</small>"),
    ("Stops so far", str(max(len(stints) - 1, 0))),
])

events = [e for e in frame["events"] if e["kind"] in ("sc", "vsc", "red")]
if events:
    st.warning(" · ".join(e["kind"].upper() + (f" — {e['detail']}" if e["detail"] else "")
                          for e in events))

left, right = st.columns([3, 2])

with left:
    theme.eyebrow("Track — the field this lap")
    rows = pd.DataFrame(trackmap.field_rows(frame))
    loop = pd.DataFrame([{**p, "i": i} for i, p in enumerate(trackmap.outline())])
    x = alt.X("x:Q", scale=alt.Scale(domain=[-2.1, 2.1]), axis=None)
    y = alt.Y("y:Q", scale=alt.Scale(domain=[-1.1, 1.1]), axis=None)
    hover = ["car:N", "team:N", "position:Q", "compound:N", "tyre_age:Q"]
    field = alt.Chart(rows)  # one dataset, every layer filters it in the spec
    track = alt.layer(
        alt.Chart(loop).mark_line(color=theme.CHART_FIELD, strokeWidth=7, opacity=0.5)
        .encode(x=x, y=y, order="i:Q"),
        # the ego's aqua ring first, so the agent is findable before anything else
        field.transform_filter(alt.datum.ego).mark_point(
            size=560, filled=False, strokeWidth=2, color=theme.ACCENT, opacity=0.9)
        .encode(x=x, y=y),
        # primary seats filled, teammates hollow — shape carries what near colours can't
        field.transform_filter(alt.datum.seat == "primary").mark_point(
            size=180, filled=True, strokeWidth=0)
        .encode(x=x, y=y, color=alt.Color("colour:N", scale=None), tooltip=hover),
        field.transform_filter(alt.datum.seat == "teammate").mark_point(
            size=180, filled=False, strokeWidth=2.2)
        .encode(x=x, y=y, color=alt.Color("colour:N", scale=None), tooltip=hover),
        # a stopped car flags itself in text ink, never a hue that means physics
        field.transform_filter(alt.datum.in_pit).mark_point(
            size=420, filled=False, strokeWidth=1.4, color=theme.TEXT, opacity=0.85)
        .encode(x=x, y=y),
    ).properties(height=330).configure_view(strokeWidth=0)
    st.altair_chart(track, width='stretch')

with right:
    theme.eyebrow(f"Order — lap {lap}")
    order = sorted(frame["cars"], key=lambda c: c["position"])
    st.dataframe(
        pd.DataFrame([
            {"Pos": c["position"],
             "Car": ("▸ " if c["id"] == EGO else "") + theme.car_label(c["id"]),
             "Team": theme.team_of(c["id"])[0],
             "Gap": "leader" if c["position"] == 1 else (
                 f"+{c['gap_ahead_s']:.1f}" if c["gap_ahead_s"] is not None else "—"),
             "Tyre": c["compound"], "Age": c["tyre_age"],
             "Pit": "IN" if c["in_pit"] else ""}
            for c in order
        ]),
        hide_index=True, width='stretch', height=330,
    )

story_col, energy_col = st.columns([3, 2])

with story_col:
    theme.eyebrow("The story so far")
    so_far = []
    for f in frames:
        if f["lap"] > lap:
            break  # never the future
        for car in f["cars"]:
            _, colour, _ = theme.team_of(car["id"])
            so_far.append({"lap": f["lap"], "car": theme.car_label(car["id"]),
                           "position": car["position"], "agent": car["id"] == EGO,
                           "colour": colour})
    data = pd.DataFrame(so_far)
    top = int(max(c["position"] for c in frames[0]["cars"]))
    axis_y = alt.Y("position:Q", title="position", scale=alt.Scale(domain=[top, 1]),
                   axis=alt.Axis(grid=True, gridColor=theme.CHART_GRID,
                                 labelColor=theme.FAINT, titleColor=theme.FAINT))
    axis_x = alt.X("lap:Q", title="lap", scale=alt.Scale(domain=[1, last_lap]),
                   axis=alt.Axis(grid=False, labelColor=theme.FAINT, titleColor=theme.FAINT))
    st.altair_chart(
        alt.layer(
            alt.Chart(data[~data["agent"]]).mark_line(strokeWidth=1, opacity=0.5)
            .encode(x=axis_x, y=axis_y, detail="car:N",
                    color=alt.Color("colour:N", scale=None)),
            alt.Chart(data[data["agent"]]).mark_line(strokeWidth=2.5, color=theme.ACCENT)
            .encode(x=axis_x, y=axis_y),
        ).properties(height=240).configure_view(strokeWidth=0),
        width='stretch',
    )

with energy_col:
    theme.eyebrow("Battery — the 4 MJ window")
    # the one saturated gradient the sheet allows: a data fill, empty-to-full
    gauge_rows = pd.DataFrame([{"soc": energy["soc_mj"], "y": "SOC"}])
    gradient = alt.Gradient(
        gradient="linear", x1=0, x2=1, y1=0, y2=0,
        stops=[alt.GradientStop(color=c, offset=i / (len(theme.SOC_RAMP) - 1))
               for i, c in enumerate(theme.SOC_RAMP)],
    )
    gauge = alt.layer(
        alt.Chart(pd.DataFrame([{"full": SOC_CAPACITY_MJ, "y": "SOC"}]))
        .mark_bar(height=26, color=theme.RAISED, cornerRadius=4)
        .encode(x=alt.X("full:Q", scale=alt.Scale(domain=[0, SOC_CAPACITY_MJ]),
                        title=None, axis=alt.Axis(grid=False, labelColor=theme.FAINT,
                                                  domainColor=theme.LINE)),
                y=alt.Y("y:N", title=None, axis=None)),
        alt.Chart(gauge_rows).mark_bar(height=26, cornerRadius=4, color=gradient)
        .encode(x="soc:Q", y=alt.Y("y:N", title=None, axis=None),
                tooltip=[alt.Tooltip("soc:Q", format=".2f", title="state of charge, MJ")]),
    ).properties(height=64).configure_view(strokeWidth=0)
    st.altair_chart(gauge, width='stretch')
    harvested = f'<span style="color:{theme.ACCENT}">▲ {energy["harvest_mj"]:.2f} MJ in</span>'
    deployed = f'<span style="color:{theme.DEPLOY}">▼ {energy["deploy_mj"]:.2f} MJ out</span>'
    st.markdown(f'<div style="font-family:ui-monospace,Menlo,monospace;font-size:0.8rem">'
                f'{harvested} &nbsp;&nbsp; {deployed}</div>', unsafe_allow_html=True)

theme.note(
    "Positions are the simulator's own lap-end classification, and the track map is an "
    "illustrative synthesis: s_track places each car by its gap when the leader crosses "
    "the line, on a loop whose shape is a visual choice, not circuit geometry (F11). "
    "Team identities are a display convention over car pairs — the simulator models "
    "seats, not constructors. Scrubbing and playing read stored frames; nothing is "
    "re-simulated (E-16)."
)
theme.footer()

if st.session_state["playing"]:
    if lap >= last_lap:
        st.session_state["playing"] = False
    else:
        time.sleep(STEP_SECONDS)
        st.session_state["playhead"] = lap + 1
        st.rerun()
