import pytest
from senna.physics.fits.gate import MissingQualityReportError, assert_quality_reports

from senna.data.quality import report_path


def _write_report(season, report_dir):
    path = report_path(season, report_dir)
    path.parent.mkdir(parents=True)
    path.write_text(f"# Data quality report — {season}\n")


def test_raises_on_missing_season_report(tmp_path):
    _write_report(2024, tmp_path)

    # F-14: no fitting starts until every season it draws on has been audited
    with pytest.raises(MissingQualityReportError, match="2025"):
        assert_quality_reports([2024, 2025], tmp_path)


def test_passes_when_all_reports_exist(tmp_path):
    for season in (2024, 2025):
        _write_report(season, tmp_path)

    assert assert_quality_reports([2024, 2025], tmp_path) is None
