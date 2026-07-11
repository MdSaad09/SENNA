"""Resolve every "Spec anchors:" ID in docs/spec/features/ to a file on disk.

The mapping is the extraction contract from docs/spec/README.md: Part 5 sections
split into docs/spec/5.<n>-*.md, Part 2 becomes 2-edge-cases.md, Part 8 becomes
8-assumptions.md, and F/A/R/T/M/OQ IDs plus bare "Part n" references stay in the
source PDF by design.
"""

import re
import sys
from pathlib import Path

PDF = "docs/spec/source/SENNA_Master_Spec_v3.pdf"

SECTION = re.compile(r"\b5\.(\d+)(?:\.\d+)?\b")
IDS = re.compile(r"\b(AR|OQ|E|F|A|R)-\d+\b")
PDF_ONLY = re.compile(r"\b[TM]\d+\b|\bPart \d\b")
LITERAL_PATH = re.compile(r"\bdocs/spec/\S+?\.md\b")

ID_HOMES = {
    "E": "docs/spec/2-edge-cases.md",
    "AR": "docs/spec/8-assumptions.md",
    "F": PDF,
    "A": PDF,
    "R": PDF,
    "OQ": PDF,
}


def anchor_targets(line):
    targets = set()
    for section in SECTION.findall(line):
        targets.add(f"docs/spec/5.{section}-*.md")
    for prefix in IDS.findall(line):
        targets.add(ID_HOMES[prefix])
    if PDF_ONLY.search(line):
        targets.add(PDF)
    for path in LITERAL_PATH.findall(line):
        targets.add(path)
    return targets


def missing_anchor_files(repo_root):
    repo_root = Path(repo_root)
    cited_by = {}
    # the underscore keeps _TEMPLATE.md out of the F*.md glob
    for feature in sorted((repo_root / "docs/spec/features").glob("F*.md")):
        for line in feature.read_text().splitlines():
            if line.startswith("Spec anchors:"):
                for target in anchor_targets(line):
                    cited_by.setdefault(target, feature.name)
    return [
        f"{target} (cited by {feature})"
        for target, feature in sorted(cited_by.items())
        if not any(repo_root.glob(target))
    ]


if __name__ == "__main__":
    missing = missing_anchor_files(Path(__file__).resolve().parents[1])
    for entry in missing:
        print(entry)
    sys.exit(1 if missing else 0)
