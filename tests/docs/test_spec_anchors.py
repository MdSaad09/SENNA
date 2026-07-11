import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_spec_anchors import missing_anchor_files


def test_every_spec_anchor_file_exists():
    # drives the F00 spec split: every anchor a feature spec cites must resolve on disk
    assert missing_anchor_files(REPO_ROOT) == []


def test_no_f1sip_in_prose():
    # rename rule (docs/spec/README.md): the project is SENNA; F1SIP survives only
    # inside the source PDF's own text, never in a filename
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()

    offenders = [path for path in tracked if "F1SIP" in path]
    for path in tracked:
        if path.startswith("docs/spec/source/"):
            continue
        if "F1SIP" in (REPO_ROOT / path).read_text(errors="ignore"):
            offenders.append(path)

    # the PDF stays untracked until F00 lands, so its on-disk name is checked directly
    offenders += [
        f"docs/spec/source/{entry.name}"
        for entry in (REPO_ROOT / "docs/spec/source").iterdir()
        if "F1SIP" in entry.name
    ]
    assert offenders == []
