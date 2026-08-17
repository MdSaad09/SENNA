"""The v1.0.0 freeze guards (F15, A-09): the two checks `make verify` runs in CI.

The report check demands purity, not just determinism: regenerating from the committed
store into a scratch directory must reproduce the committed chapter byte-for-byte, so
the check can run on a fresh clone without touching the working tree.

The chain check pins provenance internal consistency. The suite envelopes' config_hash
is COPIED from the headline manifest at eval time (senna/eval/run.py), and the configs
were legitimately comment-edited after training, so recomputing the eleven-file
fingerprint from disk would fail by design and prove nothing. What must hold instead:
every suite row names the model and hash the repo actually serves, the one live
recompute that is valid (seeds.yaml, frozen since F07) still matches, and the
harvest study's envelope matches the fingerprint it computes at run time.
"""

import json

from senna import config
from senna.eval.report import build_report

STORE = config.REPO_ROOT / "docs/results/F14/store"
COMMITTED_DOC = config.REPO_ROOT / "docs/results/F14-evaluation.md"
HEADLINE_MANIFEST = config.REPO_ROOT / "models/headline/manifest.json"
ERA2024_MANIFEST = config.REPO_ROOT / "models/era2024/manifest.json"
FREEZE_RUNBOOK = config.REPO_ROOT / "docs/freeze.md"

# these fingerprint their own overlay inputs at run time rather than copying the
# training-time manifest hash, so they chain differently below. They are the studies that
# mutate a config on purpose: claiming the frozen fingerprint would say the numbers came
# from configs they deliberately changed.
_OWN_HASH_FILES = {"harvest_sensitivity", "m2_sensitivity", "robustness"}


def test_report_reproduces_committed_doc(tmp_path):
    page = build_report(STORE, figures=True, figures_dir=tmp_path / "figures")

    # byte-for-byte against the committed chapter, with the figures rendered to a
    # scratch dir: the page's bytes must not depend on where the PNGs landed, or the
    # CI check could only pass by overwriting the committed figures
    assert page.encode() == COMMITTED_DOC.read_bytes()


def test_the_runbook_pins_the_models_the_repo_actually_ships():
    """docs/freeze.md names both model versions in the tag body, and `make verify` only
    link-checked it. F18 repointed the runbook mid-branch, retrained afterwards, and left
    it naming a generation that was then pruned from the ledger — a tag cut from that
    runbook would have frozen v1.0.0 against artifacts committed nowhere."""
    runbook = FREEZE_RUNBOOK.read_text()

    for manifest_path in (HEADLINE_MANIFEST, ERA2024_MANIFEST):
        version = json.loads(manifest_path.read_text())["model_version"]
        assert version in runbook, (
            f"docs/freeze.md does not name {version} from {manifest_path.name} — the "
            "runbook would pin a model the repo does not ship"
        )


def test_freeze_chain_is_internally_consistent():
    headline = json.loads(HEADLINE_MANIFEST.read_text())
    era2024 = json.loads(ERA2024_MANIFEST.read_text())
    seeds_now = config.fingerprint(["seeds"])

    suite_files = sorted(path for path in STORE.glob("*.json")
                         if path.stem not in _OWN_HASH_FILES)
    assert suite_files, "an empty store would make every check below vacuous"
    for path in suite_files:
        envelope = json.loads(path.read_text())["envelope"]
        # the results came from the model the repo serves, under the configs its
        # manifest fingerprinted at training time
        assert envelope["config_hash"] == headline["fingerprint"], path.name
        assert envelope["model_versions"]["headline"] == headline["model_version"], path.name
        # the one valid live recompute: seeds.yaml is frozen, so drift here is a
        # real freeze violation, never a comment edit
        assert envelope["seeds_fingerprint"] == seeds_now, path.name

    m2 = json.loads((STORE / "m2_races.json").read_text())["envelope"]
    assert m2["model_versions"]["era2024"] == era2024["model_version"]

    harvest = json.loads((STORE / "harvest_sensitivity.json").read_text())["envelope"]
    assert harvest["config_hash"] == config.fingerprint(["circuits"])
    assert harvest["seeds_fingerprint"] == seeds_now

    # the coefficient study chains the same way, on its own (wider) preimage — the
    # review found the branch's newest artifact was the one the chain never covered
    from senna.eval.coefficients import M2_CONFIG_FILES

    m2s = json.loads((STORE / "m2_sensitivity.json").read_text())["envelope"]
    assert m2s["config_hash"] == config.fingerprint(M2_CONFIG_FILES)

    assert m2s["seeds_fingerprint"] == seeds_now
    assert m2s["model_versions"]["era2024"] == era2024["model_version"]

    # the robustness arms mutate physics_params on purpose, so they chain the same way:
    # their own overlay inputs, the frozen agent they race, and the frozen seed bank
    robustness_path = STORE / "robustness.json"
    if robustness_path.is_file():
        from senna.eval.robustness import ROBUSTNESS_CONFIG_FILES

        robustness = json.loads(robustness_path.read_text())["envelope"]
        assert robustness["config_hash"] == config.fingerprint(ROBUSTNESS_CONFIG_FILES)
        assert robustness["model_versions"]["headline"] == headline["model_version"]
        assert robustness["seeds_fingerprint"] == seeds_now
