"""F-14: no model may be fitted until every season it draws on has been audited."""

from pathlib import Path

from senna.data.quality import report_path


class MissingQualityReportError(RuntimeError):
    pass


def assert_quality_reports(seasons: list[int], report_dir: str | Path) -> None:
    missing = [s for s in seasons if not report_path(s, report_dir).is_file()]
    if missing:
        raise MissingQualityReportError(
            f"no data quality report for {', '.join(map(str, missing))} under "
            f"{report_dir} — run `make ingest` for those seasons first (F-14)"
        )
