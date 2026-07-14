"""Per-season data quality report — the F-14 gate F02 reads before any fit."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DropCount:
    """What one cleaning rule did: dropped rows leave the frame, flagged ones stay."""

    rule: str
    rows_in: int
    rows_dropped: int
    rows_flagged: int


def report_path(season: int, report_dir: str | Path) -> Path:
    return Path(report_dir) / str(season) / "data_quality_report.md"


def render_report(
    season: int,
    completeness: list[dict],
    drop_counts: list[DropCount],
    missing_channels: dict[str, list[str]],
    generated_at: str,
) -> str:
    lines = [f"# Data quality report — {season}", ""]

    lines += ["## Completeness", ""]
    lines += ["| Event | Session | Source | State | Reason |", "|---|---|---|---|---|"]
    for row in completeness:
        lines.append(
            f"| {row['event']} | {row['session']} | {row['source']}"
            f" | {row['state']} | {row['reason']} |"
        )

    lines += ["", "## Rows kept vs dropped per rule", ""]
    lines += ["| Rule | Rows in | Dropped | Flagged | Kept |", "|---|---|---|---|---|"]
    for count in drop_counts:
        kept = count.rows_in - count.rows_dropped
        lines.append(
            f"| {count.rule} | {count.rows_in} | {count.rows_dropped}"
            f" | {count.rows_flagged} | {kept} |"
        )

    lines += ["", "## Channels missing per session", ""]
    if missing_channels:
        for session_label, channels in sorted(missing_channels.items()):
            lines.append(f"- {session_label}: {', '.join(channels)}")
    else:
        lines.append("- none")

    lines += ["", "## Generation metadata", ""]
    lines.append(f"- generated_at: {generated_at}")
    lines.append(f"- season: {season}")
    lines.append(f"- sessions covered: {len(completeness)}")

    return "\n".join(lines) + "\n"
