"""Gates that stand between the ingested store and a written constant.

F-14: no model may be fitted until every season it draws on has been audited. E-12, one
layer later, in two parts: no constant may be written from a store that is missing a
declared season, and no constant may be written when a season the store *does* hold
reached none of the pace fits.

The second part is the one that matches the F18 defect, and it is worth being exact about
which, because the obvious reading is wrong. The committed physics was not fitted from a
partial store. Its own watermark read "seasons 2022-2026, round 6" and its hazards blocks
counted races from every season, French GP included, which only ran in 2022. What went
missing was narrower: 2022 and 2023 laps reached the hazard, pit-loss and energy modules
and reached none of the joint pace fits, so Bahrain's era-2024 base pace was fitted on
1958 laps of an available 3705 and nothing in the file said so. A season-level gate would
have passed that run silently. This is the layer where it shows.
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


class IncompletePaceCoverageError(RuntimeError):
    pass


def assert_pace_season_coverage(reached: dict[str, set[int]], index_seasons: dict[str, set[int]]
                                ) -> None:
    """Every season the store holds for an era must reach that era's pace fits.

    The season-level gate asks whether the data is there. This asks whether the regression
    actually saw it, which is the question the committed physics failed: 2022 and 2023 sat
    in the store, passed every other module, and contributed nothing to joint pace.

    A season contributing to no circuit at all is the failure. One circuit skipped for want
    of dry slick laps is ordinary and stays quiet.
    """
    for era in sorted(index_seasons):
        seen = reached.get(era, set())
        missing = sorted(index_seasons[era] - seen)
        if missing:
            raise IncompletePaceCoverageError(
                f"era {era}: season(s) {', '.join(map(str, missing))} are in the store but "
                f"reached no joint pace fit, while "
                f"{', '.join(map(str, sorted(seen))) or 'none'} did. Base pace would be "
                "written from a sample that silently excludes them, which is the F18 "
                "defect exactly. Check the dry-session flag, Lap.era and Lap.source for "
                "those seasons before writing (E-12)"
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
