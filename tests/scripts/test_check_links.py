"""The link-rot pass `make verify` runs (F15): today's surface is INDEX's lesson links,
the risk is the new README. The checker only has to be honest about relative links —
a planted broken one must surface, a resolvable one must not.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_links import broken_links  # noqa: E402  (needs the path bootstrap above)


def test_check_links_finds_a_broken_link(tmp_path):
    (tmp_path / "lesson.md").write_text("# a page that exists\n")
    page = tmp_path / "index.md"
    page.write_text(
        "A [good link](lesson.md) beside a [rotten one](missing.md).\n"
    )

    broken = broken_links([page])

    assert [(Path(file).name, link) for file, link in broken] == [
        ("index.md", "missing.md")
    ]
