"""Gates that stand between the ingested store and a written constant.

F-14: no model may be fitted until every season it draws on has been audited. E-12, one
layer later: no constant may be written from a store that is missing a declared season.
The second gate exists because its absence already cost the project once — the committed
physics was fitted while only two of five declared seasons had landed, nothing noticed,
and the season scope went unrecorded, so `make fit` over the frozen snapshot stopped
reproducing the physics the repo ships.
"""

from pathlib import Path

from senna.data.quality import report_path


class MissingQualityReportError(RuntimeError):
    pass


class IncompleteSeasonCoverageError(RuntimeError):
    pass


def assert_quality_reports(seasons: list[int], report_dir: str | Path) -> None:
    missing = [s for s in seasons if not report_path(s, report_dir).is_file()]
    if missing:
        raise MissingQualityReportError(
            f"no data quality report for {', '.join(map(str, missing))} under "
            f"{report_dir} — run `make ingest` for those seasons first (F-14)"
        )


def assert_season_coverage(declared_seasons: list[int], ingested_seasons: list[int]) -> None:
    """Every season configs/ingest.yaml declares must actually be in the store before a
    fitted constant is written. Order does not matter — the ingested list arrives from a
    unique() over the circuit index — only which seasons are present (E-12)."""
    missing = sorted(set(declared_seasons) - set(ingested_seasons))
    if missing:
        raise IncompleteSeasonCoverageError(
            f"season(s) {', '.join(map(str, missing))} are declared in configs/ingest.yaml "
            f"but absent from the store, which holds "
            f"{', '.join(map(str, sorted(set(ingested_seasons))))} — finish `make ingest` "
            "for the missing seasons, or correct the declared list. Fitting on a partial "
            "store writes constants that the frozen snapshot cannot reproduce (E-12)"
        )
