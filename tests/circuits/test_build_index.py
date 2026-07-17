from senna.circuits.build import circuit_index


def test_index_generated_from_ingested_only():
    entries = [
        {"slug": "bahrain_grand_prix", "event_name": "Bahrain Grand Prix", "has_elevation": True},
        {"slug": "monaco_grand_prix", "event_name": "Monaco Grand Prix", "has_elevation": False},
        {"slug": "silverstone_grand_prix", "event_name": "British Grand Prix", "has_elevation": True},
    ]

    index = circuit_index(entries)

    assert index["count"] == 3
    assert len(index["circuits"]) == 3
    # the count is derived from ingested entries, never a hard-coded 22/24 calendar (F-08)
    assert index["count"] not in (22, 24)
    slugs = {circuit["slug"] for circuit in index["circuits"]}
    assert "madrid_grand_prix" not in slugs


def test_madrid_absent_until_ingested():
    without_madrid = [
        {"slug": "bahrain_grand_prix", "event_name": "Bahrain Grand Prix", "has_elevation": True},
    ]
    with_madrid = without_madrid + [
        {"slug": "madrid_grand_prix", "event_name": "Madrid Grand Prix", "has_elevation": False},
    ]

    before = circuit_index(without_madrid)
    after = circuit_index(with_madrid)

    assert "madrid_grand_prix" not in {c["slug"] for c in before["circuits"]}
    assert before["count"] == 1
    assert "madrid_grand_prix" in {c["slug"] for c in after["circuits"]}
    assert after["count"] == 2
