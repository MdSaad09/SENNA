"""The circuit library endpoints (E-13): the index is computed from what is actually
configured and fitted, never asserted. There is no ribbon pipeline on this branch, so
detail carries fit coverage rather than geometry — for each era and slick, whether the
degradation curve was fitted at this circuit or transferred from a cluster donor (T5).
That is the fact the three evaluation archetypes were chosen on.
"""

import pytest

from senna import config

SLICKS = {"SOFT", "MEDIUM", "HARD"}


def test_the_index_covers_every_configured_circuit(client):
    circuits = client.get("/api/v1/circuits").json()
    configured = config.load("circuits")
    # E-13: data-driven — Madrid appears with its first ingested session, not before
    assert len(circuits) == len(configured)
    assert {summary["id"] for summary in circuits} == set(configured)


def test_every_summary_carries_its_coverage_flag_and_energy_cap(client):
    configured = config.load("circuits")
    for summary in client.get("/api/v1/circuits").json():
        entry = configured[summary["id"]]
        assert summary["race_laps"] == entry["race_laps"]
        assert summary["h_max_mj"] == pytest.approx(entry["h_max_mj"])  # E-02, per event
        assert isinstance(summary["coverage"]["deg_fit"], bool)
        # the ribbon flag went with the pipeline; nothing may resurrect it silently
        assert "ribbon" not in summary["coverage"]


def test_an_unknown_circuit_is_a_404(client):
    assert client.get("/api/v1/circuits/nowhere_grand_prix").status_code == 404


def test_detail_reports_whether_each_tyre_fit_is_native_or_borrowed(client):
    fitted = config.load("physics_params")["circuits"]
    slug = next(iter(fitted))
    detail = client.get(f"/api/v1/circuits/{slug}").json()

    for era, block in detail["compounds"].items():
        assert set(block) <= SLICKS
        assert set(block.values()) <= {"native", "transferred"}
        for compound, provenance in block.items():
            # YAML parses the era keys as ints; JSON hands them back as strings
            block_by_era = fitted[slug]["degradation"]
            fit = (block_by_era.get(era) or block_by_era.get(int(era)))[compound]
            source = fit.get("source_circuit")
            assert provenance == ("transferred" if source else "native")


def test_the_three_evaluation_archetypes_are_natively_fitted(client):
    """The archetypes were picked because their 2026 curves are fitted at the circuit
    rather than borrowed. If a refit ever changes that, the choice needs revisiting and
    this is where it should surface."""
    for slug in ("chinese_grand_prix", "australian_grand_prix", "monaco_grand_prix"):
        detail = client.get(f"/api/v1/circuits/{slug}").json()
        era_2026 = detail["compounds"]["2026"]
        assert set(era_2026) == SLICKS, f"{slug} is missing a slick fit"
        assert set(era_2026.values()) == {"native"}, f"{slug} borrows a curve"
