

import os

import requests
import streamlit as st

API_BASE = os.environ.get("SENNA_API_BASE", "http://localhost:8000/api/v1")

# operational — a grand prix is raced inside POST /simulations and takes roughly
# eighteen seconds on Saad's machine; three minutes is an order of magnitude of headroom
# for a slower host, and short enough that a hung request fails rather than hangs
RACE_TIMEOUT_S = 180
READ_TIMEOUT_S = 30


class ApiError(RuntimeError):
    """A request the interface cannot recover from, phrased for a reader."""


def _url(path: str) -> str:
    return f"{API_BASE.rstrip('/')}/{path.lstrip('/')}"


def get(path: str, *, timeout: int = READ_TIMEOUT_S):
    try:
        response = requests.get(_url(path), timeout=timeout)
    except requests.RequestException as err:
        raise ApiError(f"could not reach the API at {API_BASE} — is it running? ({err})") from err
    if response.status_code == 404:
        return None
    if not response.ok:
        raise ApiError(f"GET {path} failed: {response.status_code} {response.text[:200]}")
    return response.json()


def post(path: str, body: dict, *, timeout: int = RACE_TIMEOUT_S):
    try:
        response = requests.post(_url(path), json=body, timeout=timeout)
    except requests.Timeout as err:
        raise ApiError(
            f"the race did not finish within {timeout}s — the API is still working on it, "
            "or the frozen model is missing from models/"
        ) from err
    except requests.RequestException as err:
        raise ApiError(f"could not reach the API at {API_BASE} — is it running? ({err})") from err
    if not response.ok:
        raise ApiError(f"POST {path} failed: {response.status_code} {response.text[:300]}")
    return response.json()


@st.cache_data(show_spinner=False)
def circuits() -> list[dict]:
    """The library. Cached: it is config, and it does not change while the app runs."""
    return get("/circuits") or []


@st.cache_data(show_spinner=False)
def circuit(slug: str) -> dict | None:
    return get(f"/circuits/{slug}")


@st.cache_data(show_spinner=False)
def run(run_id: int) -> dict | None:
    """Cached on the id: a finished run is immutable, so this is a read of a fact."""
    return get(f"/simulations/{run_id}")


@st.cache_data(show_spinner=False)
def frames(run_id: int) -> list[dict]:
    """Every lap of a finished race. Paged, because the API pages: the loop stops on the
    first short page, so a 57-lap race is one request."""
    page_size = 100
    out: list[dict] = []
    start = 1
    while True:
        page = get(f"/simulations/{run_id}/frames?from_lap={start}&to_lap={start + page_size - 1}")
        if not page:
            return out
        out.extend(page)
        if len(page) < page_size:
            return out
        start += page_size


@st.cache_data(show_spinner=False)
def decisions(run_id: int) -> list[dict]:
    return get(f"/simulations/{run_id}/decisions") or []


@st.cache_data(show_spinner=False)
def energy(run_id: int) -> dict | None:
    return get(f"/energy/{run_id}")


@st.cache_data(show_spinner=False)
def tyres(slug: str) -> list[dict]:
    return get(f"/tyres/{slug}") or []


def start_race(body: dict) -> int:
    """POST a race and wait for it. The response arrives when the race is over."""
    return post("/simulations", body)["run_id"]


def start_counterfactual(body: dict) -> tuple[int, int | None]:
    accepted = post("/counterfactuals", body)
    return accepted["run_id"], accepted.get("baseline_run_id")
