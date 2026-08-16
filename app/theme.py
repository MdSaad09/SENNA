"""One palette, and the small shared pieces every page draws with.

The colours are the ones the dashboard was built on: sampled from the reference
screenshots by decoding the PNGs and counting dominant colours, then lifted where they
had to be — `ghost` measured 2.79:1 against the ground and carries the disclaimer.
"""

import streamlit as st

# stylised — sampled from docs/reference_images/, 11 Aug 2026
GROUND = "#0b1014"
SURFACE = "#121a1f"
RAISED = "#1a242b"
LINE = "#26333c"
TEXT = "#e6edf1"
MUTED = "#c9d0d7"
FAINT = "#8a99a6"
GHOST = "#7d8994"
ACCENT = "#6bd6c3"
DANGER = "#d9556a"

# stylised — the conventional soft-to-hard ranking, invented hues, no supplier named
# anywhere in this codebase (F-29). Keys are the served compound strings.
COMPOUND_COLOURS = {
    "SOFT": "#b13f4d",
    "MEDIUM": "#b29337",
    "HARD": "#c9d0d7",
    "INTERMEDIATE": "#3f9e58",
    "WET": "#3b74c4",
}

# stylised — chart furniture, tuned to sit on the panel tones above
CHART_AXIS = "#637481"
CHART_GRID = "#1a242b"
CHART_FIELD = "#4a5a66"  # the rival cars: present, never competing for attention

DISCLAIMER = (
    "SENNA is an unofficial project and is not associated in any way with the "
    "Formula 1 companies, the FIA or any team"
)


def page(title: str, icon: str = "\N{CHEQUERED FLAG}") -> None:
    """Page config plus the styling Streamlit will not do for us. Call first, once."""
    st.set_page_config(page_title=f"SENNA — {title}", page_icon=icon, layout="wide")
    st.markdown(
        f"""
        <style>
          .stApp {{ background: {GROUND}; }}
          section[data-testid="stSidebar"] {{ background: {SURFACE}; }}
          h1, h2, h3 {{ color: {TEXT}; letter-spacing: -0.01em; }}
          .senna-eyebrow {{
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 0.68rem; letter-spacing: 0.18em; text-transform: uppercase;
            color: {ACCENT};
          }}
          .senna-note {{
            font-size: 0.78rem; line-height: 1.55; color: {GHOST};
            border-left: 2px solid {LINE}; padding-left: 0.7rem; margin: 0.4rem 0 0;
          }}
          .senna-foot {{
            font-size: 0.68rem; color: {GHOST}; border-top: 1px solid {LINE};
            padding-top: 0.6rem; margin-top: 2rem;
          }}
          div[data-testid="stMetricValue"] {{ color: {TEXT}; }}
          div[data-testid="stMetricLabel"] {{ color: {FAINT}; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def eyebrow(text: str) -> None:
    st.markdown(f'<div class="senna-eyebrow">{text}</div>', unsafe_allow_html=True)


def note(text: str) -> None:
    """A view's statement of what it is not. Spec 5.10.2 gives every view one, and the
    credibility of the whole interface rests on them being present and legible."""
    st.markdown(f'<p class="senna-note">{text}</p>', unsafe_allow_html=True)


def footer() -> None:
    st.markdown(f'<p class="senna-foot">{DISCLAIMER}</p>', unsafe_allow_html=True)


def compound_chip(compound: str) -> str:
    colour = COMPOUND_COLOURS.get(compound, GHOST)
    return (f'<span style="display:inline-block;width:9px;height:9px;'
            f'background:{colour};margin-right:6px"></span>{compound}')


def require_run() -> int | None:
    """Every page after the first needs a race. One place to say so."""
    run_id = st.session_state.get("run_id")
    if run_id is None:
        st.info("No race yet — set one up on the **Race** page and run it.")
        return None
    return run_id
