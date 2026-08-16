"""The race, lap by lap.

There is no 3D scene on this branch, and a strategy tool that never shows a race is a
worse tool. This is the same data the scene drew from — one stored frame per lap, 22 cars
with position, gap, compound and tyre age — advanced a lap at a time with the order
re-sorting beside it.

Scrubbing and playing are reads of stored frames, never re-simulations (E-16). The whole
race already finished before this page opened.
"""

import time

import altair as alt
import pandas as pd
import streamlit as st

from app import client, theme
from senna.serve.stints import stints_from_frames

EGO = 0
STEP_SECONDS = 0.35  # operational — a readable lap rate; the sim's own pace is irrelevant here

theme.page("Playback")
theme.eyebrow("Playback")
st.title("The race, lap by lap")

run_id = theme.require_run()
if run_id is None:
    theme.footer()
    st.stop()

frames = client.frames(run_id)
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

head = st.columns(5)
head[0].metric("Lap", f"{lap} / {last_lap}")
head[1].metric("Position", f"P{agent['position']}")
head[2].metric("Tyre", f"{agent['compound']} · {agent['tyre_age']}L")
head[3].metric("Battery", f"{frame['agent']['soc_mj']:.2f} MJ")
head[4].metric("Stops so far", max(len(stints) - 1, 0))

events = [e for e in frame["events"] if e["kind"] in ("sc", "vsc", "red")]
if events:
    st.warning(" · ".join(e["kind"].upper() + (f" — {e['detail']}" if e["detail"] else "")
                          for e in events))

left, right = st.columns([3, 2])

with left:
    # the field's positions up to the playhead: the story so far, never the future
    so_far = [
        {"lap": f["lap"], "car": car["id"], "position": car["position"],
         "agent": car["id"] == EGO}
        for f in frames if f["lap"] <= lap for car in f["cars"]
    ]
    data = pd.DataFrame(so_far)
    top = int(max(c["position"] for c in frames[0]["cars"]))
    axis_y = alt.Y("position:Q", title="position", scale=alt.Scale(domain=[top, 1]),
                   axis=alt.Axis(grid=True, gridColor=theme.CHART_GRID,
                                 labelColor=theme.FAINT, titleColor=theme.FAINT))
    axis_x = alt.X("lap:Q", title="lap", scale=alt.Scale(domain=[1, last_lap]),
                   axis=alt.Axis(grid=False, labelColor=theme.FAINT, titleColor=theme.FAINT))
    st.altair_chart(
        alt.layer(
            alt.Chart(data[~data["agent"]]).mark_line(
                strokeWidth=1, opacity=0.4, color=theme.CHART_FIELD
            ).encode(x=axis_x, y=axis_y, detail="car:N"),
            alt.Chart(data[data["agent"]]).mark_line(
                strokeWidth=2.5, color=theme.ACCENT
            ).encode(x=axis_x, y=axis_y),
        ).properties(height=320).configure_view(strokeWidth=0),
        width='stretch',
    )

with right:
    order = sorted(frame["cars"], key=lambda c: c["position"])
    st.dataframe(
        pd.DataFrame([
            {"Pos": c["position"],
             "Car": ("▸ " if c["id"] == EGO else "") + f"C{c['id'] + 1:02d}",
             "Gap": "leader" if c["position"] == 1 else (
                 f"+{c['gap_ahead_s']:.1f}" if c["gap_ahead_s"] is not None else "—"),
             "Tyre": c["compound"], "Age": c["tyre_age"],
             "Pit": "IN" if c["in_pit"] else ""}
            for c in order
        ]),
        hide_index=True, width='stretch', height=320,
    )

theme.note(
    "Positions are the simulator's own lap-end classification. The simulator is "
    "lap-quantised, so there is no within-lap ordering to show and none is invented here. "
    "Scrubbing and playing read stored frames; nothing is re-simulated (E-16)."
)
theme.footer()

if st.session_state["playing"]:
    if lap >= last_lap:
        st.session_state["playing"] = False
    else:
        time.sleep(STEP_SECONDS)
        st.session_state["playhead"] = lap + 1
        st.rerun()
