
import altair as alt
import pandas as pd
import streamlit as st

from app import client, theme

EGO = 0

# stylised — the wording only. Each entry reads the comment beside that dim in
# senna/explain/features.py, and the mapping is keyed by the served name, so a renamed
# feature falls through to its raw name rather than silently mislabelling a bar.
FEATURE_LABELS = {
    "lap_progress": "how far into the race", "position_frac": "track position",
    "places_gained_frac": "places gained since the grid", "compound_is_soft": "on softs",
    "compound_is_medium": "on mediums", "compound_is_hard": "on hards",
    "compound_is_inter": "on intermediates", "compound_is_wet": "on wets",
    "tyre_age_norm": "tyre age", "tyre_grip_est": "grip left",
    "tyre_temp_state": "tyre temperature state", "pit_count_norm": "stops made",
    "second_compound_used": "second compound used", "fuel_frac": "fuel remaining",
    "soc_frac": "battery charge", "last_lap_harvest_frac": "energy recovered last lap",
    "last_lap_deploy_frac": "energy spent last lap", "gap_ahead_norm": "gap to the car ahead",
    "gap_behind_norm": "gap to the car behind",
    "ahead_tyre_age_delta": "tyre age vs the car ahead",
    "ahead_compound_hardness_delta": "compound vs the car ahead",
    "behind_tyre_age_delta": "tyre age vs the car behind",
    "override_window": "manual override available", "status_green": "green flag",
    "status_vsc": "virtual safety car", "status_sc": "safety car",
    "pit_lane_open": "pit lane open", "weather_dry": "dry", "weather_damp": "damp",
    "weather_wet": "wet", "wetness": "how wet the track is",
    "track_temp_norm": "track temperature",
}

REWARD_LABELS = {
    "pace": "pace shaping",
    "position": "position (potential-based)",
    "terminal": "terminal points",
}

PIT_CALLS = ["stay out", "pit for Soft", "pit for Medium", "pit for Hard",
             "pit for Intermediate", "pit for Wet"]
MODE_CALLS = ["conserve energy", "run balanced", "attack", "defend"]

theme.page("Explainability")
theme.eyebrow("Explainability")
st.title("Why the agent made this call")

run_id = theme.require_run()
if run_id is None:
    theme.footer()
    st.stop()

cards = client.decisions(run_id)
frames = client.frames(run_id)
run = client.run(run_id) or {}

if not cards:
    # E-15: a retrained model explains only its own runs
    st.warning(
        f"No stored explanations for model version {run.get('model_version', 'unknown')}. "
        "A retrained model explains only its own runs — run `make explain` for this "
        "checkpoint."
    )
    theme.footer()
    st.stop()

laps = [card["lap"] for card in cards]

# pick the lap ON the race itself: the ego's position trace with a dot per carded
# lap, pit calls in aqua. A click selects; the slider stays as the accessible path
# and the fallback when nothing is picked.
position_at = {
    f["lap"]: next(c["position"] for c in f["cars"] if c["id"] == EGO) for f in frames
}
ego_trace = pd.DataFrame([{"lap": lap, "position": pos}
                          for lap, pos in position_at.items()])
by_lap = {c["lap"]: c for c in cards}
last_position = position_at[max(position_at)]
dots = pd.DataFrame([
    # cards count laps from 0 and frames from 1 (the F23 join), so the dot draws at
    # frame_lap while the selection keeps the card's own lap; a card past the final
    # frame parks at the last known position rather than vanishing off the chart
    {"lap": lap, "frame_lap": lap + 1,
     "position": position_at.get(lap + 1, last_position),
     "pit": by_lap[lap]["action"]["pit"] > 0}
    for lap in laps
])
picker = alt.selection_point(fields=["lap"], name="lap_pick")
top = int(ego_trace["position"].max())
pick_chart = alt.layer(
    alt.Chart(ego_trace).mark_line(strokeWidth=1.5, color=theme.CHART_FIELD)
    .encode(x=alt.X("lap:Q", title="lap",
                    axis=alt.Axis(grid=False, labelColor=theme.FAINT, titleColor=theme.FAINT)),
            y=alt.Y("position:Q", title=None, scale=alt.Scale(domain=[top, 1]),
                    axis=alt.Axis(grid=True, gridColor=theme.CHART_GRID,
                                  labelColor=theme.FAINT))),
    alt.Chart(dots).mark_point(size=90, filled=True)
    .encode(x="frame_lap:Q", y="position:Q",
            color=alt.condition(alt.datum.pit, alt.value(theme.ACCENT),
                                alt.value(theme.COAST)),
            tooltip=[alt.Tooltip("lap:Q", title="decision lap")])
    .add_params(picker),
).properties(height=140).configure_view(strokeWidth=0)
picked = st.altair_chart(pick_chart, width='stretch', on_select="rerun",
                         selection_mode="lap_pick", key="lap_pick_chart")
picked_laps = [p["lap"] for p in picked.selection.get("lap_pick", []) if "lap" in p] \
    if picked and picked.selection else []

slider_lap = st.select_slider("Lap", options=laps, value=laps[0],
                              label_visibility="collapsed")
chosen_lap = picked_laps[0] if picked_laps else slider_lap
if picked_laps:
    st.caption(f"lap {chosen_lap} picked on the chart — clear the selection "
               "to drive with the slider")
card = next(c for c in cards if c["lap"] == chosen_lap)

theme.card(card["decision"], card["plain_language"])

# primary: the reward decomposition
theme.eyebrow("Reward decomposition — primary")
# cards number laps from 0 (the observation's lap index at decision time) and frames
# from 1, so the frame for a decision is the next one along
frame = next((f for f in frames if f["lap"] == card["lap"] + 1), None)
terms = (frame or {}).get("agent", {}).get("reward_terms") or {}
named = {k: v for k, v in terms.items() if k != "total"}

if not named:
    st.caption("no reward terms stored for this lap")
else:
    rows = pd.DataFrame([
        {"term": REWARD_LABELS.get(k, k), "value": v} for k, v in named.items()
    ])
    st.altair_chart(
        alt.Chart(rows).mark_bar(height=22, color=theme.ACCENT).encode(
            x=alt.X("value:Q", title=None,
                    axis=alt.Axis(grid=True, gridColor=theme.CHART_GRID,
                                  labelColor=theme.FAINT)),
            y=alt.Y("term:N", title=None, sort=None,
                    axis=alt.Axis(labelColor=theme.MUTED, domainColor=theme.LINE)),
            tooltip=["term", alt.Tooltip("value:Q", format=".4f")],
        ).properties(height=110).configure_view(strokeWidth=0),
        width='stretch',
    )
    if "total" in terms:
        st.caption(f"total {terms['total']:.4f}")
theme.note(
    "Every term the environment served for this lap, and no others. The reward has three "
    "and legality is not among them: compliance comes from the action mask, not from a "
    "penalty the agent could learn to trade against."
)

# secondary: what else was available
st.divider()
theme.eyebrow("Alternatives the policy weighed — secondary")

def head_table(name: str, labels: list[str], probs: list[float],
               legal: list[bool], chosen: int) -> pd.DataFrame:
    return pd.DataFrame([
        {"": "▸" if i == chosen else "",
         "Action": labels[i],
         "Probability": (f"{probs[i] * 100:.1f}%" if legal[i] else "masked"),
         "Legal": "yes" if legal[i] else "no"}
        for i in sorted(range(len(labels)), key=lambda i: -probs[i])
    ])

left, right = st.columns(2)
with left:
    st.caption("pit head")
    st.dataframe(head_table("pit", PIT_CALLS, card["probs"]["pit"],
                            card["masks"]["pit"], card["action"]["pit"]),
                 hide_index=True, width='stretch')
with right:
    st.caption("energy mode head")
    st.dataframe(head_table("mode", MODE_CALLS, card["probs"]["mode"],
                            card["masks"]["mode"], card["action"]["mode"]),
                 hide_index=True, width='stretch')

if card.get("flip"):
    st.caption("what would have changed it")
    for line in card["flip"]:
        st.markdown(f"- {line}")

theme.note(
    "These are the masked policy probabilities for this one lap, not a search over whole "
    "strategies — the agent never enumerated a race plan. Actions marked not legal were "
    "forbidden by the action mask before the policy chose."
)

# exploratory: SHAP
st.divider()
with st.expander("Feature attribution (SHAP) — exploratory", expanded=False):
    honesty = card.get("honesty", {})
    fidelity = honesty.get("fidelity", {})
    if fidelity:
        st.caption(" · ".join(f"{head} agreement {value * 100:.2f}%"
                              for head, value in fidelity.items()))
    for head in ("pit", "mode"):
        drivers = card.get("drivers", {}).get(head) or []
        if not drivers:
            continue
        st.caption(f"{head} head — top drivers")
        rows = pd.DataFrame([
            {"feature": FEATURE_LABELS.get(name, name), "shap": value}
            for name, value in drivers
        ])
        st.altair_chart(
            alt.Chart(rows).mark_bar(height=18).encode(
                x=alt.X("shap:Q", title=None,
                        axis=alt.Axis(grid=True, gridColor=theme.CHART_GRID,
                                      labelColor=theme.FAINT)),
                y=alt.Y("feature:N", title=None, sort=None,
                        axis=alt.Axis(labelColor=theme.MUTED, domainColor=theme.LINE)),
                color=alt.condition(alt.datum.shap > 0, alt.value(theme.ACCENT),
                                    alt.value(theme.DANGER)),
                tooltip=["feature", alt.Tooltip("shap:Q", format=".3f")],
            ).properties(height=22 * len(rows) + 20).configure_view(strokeWidth=0),
            width='stretch',
        )
    st.markdown(f'<p class="senna-note">{honesty.get("statement", "")}</p>',
                unsafe_allow_html=True)
    theme.note(
        "Exploratory, and third in this page's order on purpose. SHAP is computed against "
        "a surrogate model fitted to the agent's decisions, not against the policy network, "
        "so it explains something that agrees with the agent to the measured percentage "
        "above — not the agent itself."
    )

theme.footer()
