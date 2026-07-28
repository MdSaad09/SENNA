"""The link-rot pass `make verify` runs (F15): every relative markdown link in the
public-facing pages must resolve from the file that carries it. External URLs are out
of scope — checking them needs the network, and `make verify` must stay runnable on a
clean offline clone.

    python scripts/check_links.py README.md INDEX.md docs/**/*.md
"""

import re
import sys
from pathlib import Path

# [text](target) minus images' leading !, code spans excluded by the markdown grammar
# closely enough for this repo's plain pages
_LINK = re.compile(r"\[[^\]]*\]\(([^)#\s]+)[^)]*\)")


def broken_links(md_paths) -> list:
    """(file, link) for every relative link whose target does not exist on disk."""
    rotten = []
    for path in md_paths:
        path = Path(path)
        for target in _LINK.findall(path.read_text()):
            if "://" in target or target.startswith("mailto:"):
                continue
            if not (path.parent / target).exists():
                rotten.append((str(path), target))
    return rotten


def main() -> int:
    paths = [Path(arg) for arg in sys.argv[1:]]
    if not paths:
        print("usage: check_links.py <markdown files>", file=sys.stderr)
        return 2
    rotten = broken_links(paths)
    for file, link in rotten:
        print(f"{file}: broken link -> {link}")
    if not rotten:
        print(f"{len(paths)} files, every relative link resolves")
    return 1 if rotten else 0


if __name__ == "__main__":
    raise SystemExit(main())
