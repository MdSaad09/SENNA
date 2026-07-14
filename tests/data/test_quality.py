import dataclasses
from pathlib import Path

import pytest
from senna.data.quality import DropCount, render_report, report_path

SECTION_HEADINGS = (
    "## Completeness",
    "## Rows kept vs dropped per rule",
    "## Channels missing per session",
    "## Generation metadata",
)


def _sample_report() -> str:
    return render_report(
        season=2024,
        completeness=[
            {
                "event": "Bahrain Grand Prix",
                "session": "Race",
                "source": "fastf1",
                "state": "loaded",
                "reason": "",
            },
            {
                "event": "Sao Paulo Grand Prix",
                "session": "Race",
                "source": "fastf1",
                "state": "excluded",
                "reason": "wet race, analysed separately (5.3.4)",
            },
        ],
        drop_counts=[
            DropCount(rule="is_accurate", rows_in=1210, rows_dropped=37, rows_flagged=0),
            DropCount(rule="is_green", rows_in=1173, rows_dropped=0, rows_flagged=84),
        ],
        missing_channels={"Bahrain Grand Prix — Race": ["DRS"]},
        generated_at="2026-07-14T12:00:00Z",
    )


def test_report_renders_all_four_sections():
    report = _sample_report()

    assert report.splitlines()[0] == "# Data quality report — 2024"
    for heading in SECTION_HEADINGS:
        assert heading in report


def test_per_rule_drop_counts_land_in_the_report():
    report = _sample_report()

    is_accurate_line = next(line for line in report.splitlines() if "is_accurate" in line)
    assert "1210" in is_accurate_line
    assert "37" in is_accurate_line
    is_green_line = next(line for line in report.splitlines() if "is_green" in line)
    assert "84" in is_green_line


def test_exclusions_and_channel_gaps_are_spelled_out():
    report = _sample_report()

    # acceptance: excluded means excluded *with a written reason*
    assert "wet race, analysed separately (5.3.4)" in report
    assert "DRS" in report
    assert "2026-07-14T12:00:00Z" in report


def test_report_path_resolves_inside_the_configured_report_dir():
    report_dir = "docs/data_quality"  # quality.report_dir (configs/ingest.yaml)

    assert report_path(2024, report_dir) == Path("docs/data_quality/2024/data_quality_report.md")


def test_drop_count_is_frozen():
    count = DropCount(rule="is_accurate", rows_in=10, rows_dropped=1, rows_flagged=0)

    with pytest.raises(dataclasses.FrozenInstanceError):
        count.rows_dropped = 0
