"""The petrol design system — tokens, gradients and the small pieces every page draws with.

Every hex below is sourced from the two reference sheets Saad supplied on 19 Aug 2026
(docs/reference_images/SENNA_petrol_palette_reference.png and SENNA_gradient_system.png),
which replaced the sampled F23 palette wholesale. The sheets carry the rules as well as
the colours: team colour answers WHO, aqua and ember answer WHAT, and they never take
the same visual role in one view; ember stays out of navigation chrome; a gradient may
be saturated only inside a data fill; nothing under 40px wears a gradient at all.
"""

import streamlit as st

# core tokens — sourced, SENNA_petrol_palette_reference.png
GROUND = "#0A1014"
SURFACE = "#101A20"
RAISED = "#17242C"
LINE = "#22333D"
TEXT = "#E4EDF2"
MUTED = "#93A8B4"
FAINT = "#5E7583"

# the accent axis is the physics — sourced, same sheet. Aqua for harvest and the
# resting UI accent; ember for deployment and energy events only; coast reads grey
# by design (it is the neutral of the axis); alert for limit breach.
ACCENT = "#2ED9C3"
DEPLOY = "#FF7A3D"
COAST = "#7A8C99"
DANGER = "#FF3B5C"

# state of charge, empty to full — sourced; luminance-monotone (validated 19 Aug)
SOC_RAMP = ("#0F3B3F", "#14666A", "#1D9A93", "#46C9AE", "#8FE3C0")

# Constructor identity — sourced. SENNA itself is the eleventh team: the ego carries
# the aqua harvest identity so the agent is findable in any view, and the ten sheet
# constructors fill the rest of the grid. The teammate hex is the sheet's lifted
# variant, drawn hollow wherever shape can carry the distinction. Team grouping over
# car ids is a display convention (the simulator models seats, not constructors) and
# every view that uses it says so.
TEAMS = (
    # the teammate lift is NOT the SOC ramp's full step: one hex may not answer
    # "who" on the map and "what" on the gauge in the same view (the sheet's rule)
    ("SENNA", ACCENT, "#7CE7D4"),
    ("Red Bull Racing", "#5A7FE8", "#93ABF0"),
    ("Ferrari", "#E4243C", "#ED7080"),
    ("Mercedes", "#A8B8C4", "#C6D0D8"),
    ("McLaren", "#FF9E1B", "#FFBF6A"),
    ("Aston Martin", "#2FA96B", "#77C79E"),
    ("Alpine", "#F05CA0", "#F595C1"),
    ("Williams", "#2C9CDB", "#75BEE7"),
    ("Racing Bulls", "#93A9F5", "#B8C7F8"),
    ("Kick Sauber", "#6FD84A", "#A1E589"),
    ("Haas", "#E2E6EA", "#ECEEF1"),
)


def team_of(car_id: int) -> tuple[str, str, bool]:
    """Car pairs: team car_id // 2, the odd seat is the teammate on the lifted hex."""
    name, primary, teammate = TEAMS[car_id // 2]
    is_teammate = car_id % 2 == 1
    return name, (teammate if is_teammate else primary), is_teammate


def car_label(car_id: int) -> str:
    return f"C{car_id + 1:02d}"


# stylised — the conventional soft-to-hard ranking, invented hues, no supplier named
# anywhere in this codebase (F-29). Keys are the served compound strings.
COMPOUND_COLOURS = {
    "SOFT": "#E05066",       # rose, deliberately NOT the alert token — status stays reserved
    "MEDIUM": "#F2B33D",
    "HARD": "#E4EDF2",
    "INTERMEDIATE": "#2FA96B",
    "WET": "#2C9CDB",
}

# stylised — chart furniture tuned to the petrol surfaces: the axis/grid recede,
# the field never competes with the ego's aqua. Not on the sheets; ours to own.
CHART_AXIS = FAINT
CHART_GRID = "#152028"
CHART_FIELD = "#3A4B57"
GHOST = FAINT  # kept name: the low-emphasis ink some pages import

DISCLAIMER = (
    "SENNA is an unofficial project and is not associated in any way with the "
    "Formula 1 companies, the FIA or any team"
)

# the ambient canvas — sourced, SENNA_gradient_system.png. One glow at a time, never
# more than 12% over the base, and it never sits behind a chart well. The glow reads
# the car's energy state: aqua anchored top-left while harvesting, ember crossing to
# top-right while deploying, a cold neutral otherwise.
_GLOWS = {
    "neutral": "radial-gradient(120% 90% at 50% -10%, #1B3742 0%, transparent 60%)",
    "harvesting": "radial-gradient(120% 90% at 14% -5%, rgba(46,217,195,.115) 0%, transparent 60%)",
    "deploying": "radial-gradient(120% 90% at 86% -5%, rgba(255,122,61,.095) 0%, transparent 60%)",
}
_BASE = "linear-gradient(160deg, #0D161C, #070C0F)"


def page(title: str, icon: str = "\N{CHEQUERED FLAG}") -> None:
    """Page config plus the styling Streamlit will not do for us. Call first, once."""
    st.set_page_config(page_title=f"SENNA — {title}", page_icon=icon, layout="wide")
    st.markdown(
        f"""
        <style>
          .stApp {{ background: {_GLOWS["neutral"]}, {_BASE}; background-attachment: fixed; }}
          header[data-testid="stHeader"] {{ background: transparent; }}
          #MainMenu, footer {{ visibility: hidden; }}
          section[data-testid="stSidebar"] {{
            background: linear-gradient(180deg, #142027, #0F181E);
            border-right: 1px solid {LINE};
          }}
          h1, h2, h3 {{ color: {TEXT}; letter-spacing: -0.01em; }}
          h1 {{ font-size: 1.9rem; }}
          .senna-eyebrow {{
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 0.68rem; letter-spacing: 0.18em; text-transform: uppercase;
            color: {ACCENT}; margin-bottom: 0.15rem;
          }}
          .senna-headline {{
            font-size: 1.5rem; font-weight: 650; color: {TEXT};
            letter-spacing: -0.01em; margin: 0.1rem 0 0.6rem;
          }}
          .senna-headline .sep {{ color: {FAINT}; padding: 0 0.35rem; }}
          .senna-stats {{ display: flex; gap: 0.75rem; flex-wrap: wrap; margin: 0.4rem 0 0.8rem; }}
          .senna-stat {{
            flex: 1 1 0; min-width: 96px; padding: 0.55rem 0.8rem;
            background: linear-gradient(180deg, {RAISED}, #141F26);
            border: 1px solid {LINE}; border-radius: 8px;
          }}
          .senna-stat .k {{
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 0.62rem; letter-spacing: 0.14em; text-transform: uppercase;
            color: {FAINT};
          }}
          .senna-stat .v {{
            font-size: 1.35rem; font-weight: 650; color: {TEXT}; line-height: 1.3;
          }}
          .senna-stat .v small {{ font-size: 0.8rem; color: {MUTED}; font-weight: 500; }}
          .senna-card {{
            background: linear-gradient(180deg, #1A2830, #141F26);
            border: 1px solid {LINE}; border-radius: 10px;
            padding: 0.9rem 1.1rem; margin: 0.4rem 0;
            border-top: 3px solid {ACCENT};
          }}
          .senna-card .call {{ font-size: 1.25rem; font-weight: 650; color: {TEXT}; }}
          .senna-card .why {{ font-size: 0.85rem; color: {MUTED}; margin-top: 0.25rem; }}
          .senna-note {{
            font-size: 0.78rem; line-height: 1.55; color: {FAINT};
            border-left: 2px solid {LINE}; padding-left: 0.7rem; margin: 0.4rem 0 0;
          }}
          .senna-foot {{
            font-size: 0.68rem; color: {FAINT}; border-top: 1px solid {LINE};
            padding-top: 0.6rem; margin-top: 2rem;
          }}
          .senna-chip {{
            display: inline-block; padding: 0.05rem 0.5rem; border-radius: 99px;
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 0.68rem; letter-spacing: 0.06em;
            border: 1px solid {LINE}; color: {MUTED}; margin-right: 0.3rem;
          }}
          div[data-testid="stMetricValue"] {{ color: {TEXT}; }}
          div[data-testid="stMetricLabel"] {{ color: {FAINT}; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def ambient(state: str) -> None:
    """Re-key the canvas glow to the car's energy state (playback ticks call this).

    The 800ms cross-fade of the reference sheet cannot survive Streamlit's rerender,
    so each tick paints the destination state directly — the migration reads at the
    lap rate instead. One glow at a time, per the sheet's limits.
    """
    glow = _GLOWS.get(state, _GLOWS["neutral"])
    st.markdown(
        f"<style>.stApp {{ background: {glow}, {_BASE}; background-attachment: fixed; }}</style>",
        unsafe_allow_html=True,
    )


def eyebrow(text: str) -> None:
    st.markdown(f'<div class="senna-eyebrow">{text}</div>', unsafe_allow_html=True)


def headline(text: str) -> None:
    """The race headline, rendered verbatim — the composed string IS the artifact,
    and tests match it exactly, so no markup is injected into it."""
    st.markdown(f'<div class="senna-headline">{text}</div>', unsafe_allow_html=True)


def stats(rows: list[tuple[str, str]]) -> None:
    """The stat tiles that replace stock st.metric — one flex row, petrol cards."""
    cells = "".join(
        f'<div class="senna-stat"><div class="k">{k}</div><div class="v">{v}</div></div>'
        for k, v in rows
    )
    st.markdown(f'<div class="senna-stats">{cells}</div>', unsafe_allow_html=True)


def card(call: str, why: str = "", rule_colour: str = ACCENT) -> None:
    """A raised card with the team rule on its top edge — the decision unit."""
    why_html = f'<div class="why">{why}</div>' if why else ""
    st.markdown(
        f'<div class="senna-card" style="border-top-color:{rule_colour}">'
        f'<div class="call">{call}</div>{why_html}</div>',
        unsafe_allow_html=True,
    )


def note(text: str) -> None:
    """A view's statement of what it is not. Spec 5.10.2 gives every view one, and the
    credibility of the whole interface rests on them being present and legible."""
    st.markdown(f'<p class="senna-note">{text}</p>', unsafe_allow_html=True)


def footer() -> None:
    st.markdown(f'<p class="senna-foot">{DISCLAIMER}</p>', unsafe_allow_html=True)


def compound_chip(compound: str) -> str:
    colour = COMPOUND_COLOURS.get(compound, FAINT)
    return (f'<span style="display:inline-block;width:9px;height:9px;'
            f'background:{colour};margin-right:6px"></span>{compound}')


def require_run() -> int | None:
    """Every page after the first needs a race. One place to say so."""
    run_id = st.session_state.get("run_id")
    if run_id is None:
        st.info("No race yet — set one up on the **Race** page and run it.")
        return None
    return run_id
