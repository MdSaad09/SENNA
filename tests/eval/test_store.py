"""The committed run store (A-09, plan deliverable 7). `make report` is a pure function
of what lands here, which only holds if a rewrite of the same numbers produces the same
bytes — no timestamps, no dict-order drift — and if every row carries enough provenance
to say which model, which configs, which seeds and which commit produced it.
"""

import json

from senna.eval.store import envelope, read_metric, repo_commit, write_metric

MODEL_VERSIONS = {
    "headline": "senna-ppo-6b6edb78d84e-C-00835584",
    "era2024": "senna-ppo-6b6edb78d84e-era2024-C-02000000",
}
CONFIG_HASH = "ab" * 32
SEEDS_FINGERPRINT = "cd" * 32


def a09_envelope():
    return envelope(
        model_versions=MODEL_VERSIONS,
        config_hash=CONFIG_HASH,
        seeds_fingerprint=SEEDS_FINGERPRINT,
    )


def test_write_metric_is_byte_identical_on_rewrite(tmp_path):
    payload = {"mean_delta": 1.25, "n": 480, "per_circuit": {"monza": 2, "bahrain": 1}}
    same_payload_other_order = {
        "per_circuit": {"bahrain": 1, "monza": 2}, "n": 480, "mean_delta": 1.25,
    }

    first = write_metric(tmp_path, "m1_pairs", payload, envelope=a09_envelope())
    written = first.read_bytes()
    second = write_metric(tmp_path, "m1_pairs", same_payload_other_order, envelope=a09_envelope())

    assert second == first
    assert second.read_bytes() == written


def test_store_rows_carry_the_a09_envelope(tmp_path):
    stamped = a09_envelope()

    assert stamped["model_versions"] == MODEL_VERSIONS
    assert stamped["config_hash"] == CONFIG_HASH
    assert stamped["seeds_fingerprint"] == SEEDS_FINGERPRINT
    assert stamped["git_commit"] == repo_commit()
    assert stamped["git_commit"]  # a number nobody can trace back to a commit is not evidence

    payload = {"utilisation": 0.93, "derate_share": 0.01}
    path = write_metric(tmp_path, "m4_energy", payload, envelope=stamped)
    row = read_metric(tmp_path, "m4_energy")

    assert row["envelope"] == stamped
    assert row["payload"] == payload
    assert json.loads(path.read_text()) == row
