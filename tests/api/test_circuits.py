"""The circuit library endpoints (E-13): counts and coverage computed from what is
actually ingested and built, detail metadata straight from the F04 meta.json, and the
ribbon URL relative so no server-side hostname can leak into a payload (F-27).
"""

import json

import pytest

from senna import config
from tests.api.conftest import CIRCUIT

BUILT_DIR = config.REPO_ROOT / "data" / "circuits" / CIRCUIT

_built_guard = pytest.mark.skipif(
    not (BUILT_DIR / "meta.json").is_file() or not (BUILT_DIR / "ribbon.glb").is_file(),
    reason="needs the built bahrain circuit artifacts (data/circuits)",
)


def test_the_index_covers_every_configured_circuit(client):
    circuits = client.get("/api/v1/circuits").json()
    configured = config.load("circuits")
    # E-13: data-driven — Madrid appears with its first ingested session, not before
    assert len(circuits) == len(configured)
    assert {summary["id"] for summary in circuits} == set(configured)


def test_every_summary_carries_coverage_flags_and_the_energy_cap(client):
    configured = config.load("circuits")
    for summary in client.get("/api/v1/circuits").json():
        entry = configured[summary["id"]]
        assert summary["race_laps"] == entry["race_laps"]
        assert summary["h_max_mj"] == pytest.approx(entry["h_max_mj"])  # E-02, per event
        assert isinstance(summary["coverage"]["ribbon"], bool)
        assert isinstance(summary["coverage"]["deg_fit"], bool)


def test_an_unknown_circuit_is_a_404(client):
    assert client.get("/api/v1/circuits/nowhere_grand_prix").status_code == 404


@_built_guard
def test_coverage_reports_ribbons_only_where_one_was_built(client):
    circuits = {summary["id"]: summary for summary in client.get("/api/v1/circuits").json()}
    assert circuits[CIRCUIT]["coverage"]["ribbon"] is True

    unbuilt = [
        summary for slug, summary in circuits.items()
        if not (config.REPO_ROOT / "data" / "circuits" / slug / "ribbon.glb").is_file()
    ]
    assert unbuilt, "every circuit has a ribbon — this negative case needs a new subject"
    assert all(summary["coverage"]["ribbon"] is False for summary in unbuilt)


@_built_guard
def test_detail_embeds_the_f04_annotations_and_a_relative_ribbon_url(client):
    meta = json.loads((BUILT_DIR / "meta.json").read_text())
    detail = client.get(f"/api/v1/circuits/{CIRCUIT}").json()

    # relative, no scheme, no host: the F-27 fence against baked-in server hostnames
    assert detail["gltf_url"] == f"/api/v1/assets/circuits/{CIRCUIT}/ribbon.glb"
    assert detail["lap_length_m"] == pytest.approx(meta["lap_length_m"])
    assert detail["corners"] == meta["corners"]
    assert detail["braking_zones"] == meta["braking_zones"]
    assert detail["xmode_sections"] == meta["xmode_sections"]
    assert detail["h_max_mj"] == pytest.approx(config.load("circuits")[CIRCUIT]["h_max_mj"])
    # and the static mount actually serves the GLB the URL points at
    assert client.get(detail["gltf_url"]).status_code == 200


def test_an_unbuilt_circuit_has_no_ribbon_url(client):
    unbuilt = next(
        slug for slug in config.load("circuits")
        if not (config.REPO_ROOT / "data" / "circuits" / slug / "ribbon.glb").is_file()
    )
    detail = client.get(f"/api/v1/circuits/{unbuilt}").json()
    assert detail["gltf_url"] is None


@_built_guard
def test_detail_passes_the_meta_flags_through_verbatim(client):
    # F11 divergence 1: the View 1 legend derives its stylised/inferred caveats
    # from these flags instead of hardcoded copy (5.9.2, 5.10.2 row 1)
    meta = json.loads((BUILT_DIR / "meta.json").read_text())
    detail = client.get(f"/api/v1/circuits/{CIRCUIT}").json()
    assert detail["flags"] == meta["flags"]


def test_a_circuit_without_meta_reports_null_flags(client):
    no_meta = next(
        slug for slug in config.load("circuits")
        if not (config.REPO_ROOT / "data" / "circuits" / slug / "meta.json").is_file()
    )
    detail = client.get(f"/api/v1/circuits/{no_meta}").json()
    assert detail["flags"] is None
