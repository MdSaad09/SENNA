"""The throughput benchmark (5.6.2): steps/s across N workers, the number that prices
F07's training plan. The report must carry enough provenance to reproduce a reading —
hardware, python, commit and a hash of the exact configs the env was built from — so a
steps/s figure in the decisions log can never be read out of context.
"""

import re

import pytest

from senna.bench.throughput import run_benchmark

CIRCUIT = "bahrain_grand_prix"
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_KEYS = {
    "steps_s_aggregate",
    "steps_s_per_worker",
    "workers",
    "total_steps",
    "warmup_steps",
    "wall_s",
    "circuit",
    "era",
    "policy",
    "hardware",
    "python",
    "commit",
    "config_hash",
    "projected_8m_hours",
}


def test_the_bench_report_carries_hardware_commit_and_config_hash():
    report = run_benchmark(
        workers=1, total_steps=64, warmup_steps=8, circuit=CIRCUIT, vec="dummy"
    )

    assert _REQUIRED_KEYS <= set(report)
    assert report["workers"] == 1
    assert report["circuit"] == CIRCUIT
    assert report["steps_s_aggregate"] > 0
    assert report["wall_s"] > 0
    assert _SHA256_HEX.match(report["config_hash"])

    hardware = report["hardware"]
    assert {"platform", "machine", "cpu_count"} <= set(hardware)
    assert isinstance(hardware["cpu_count"], int)


@pytest.mark.slow
def test_the_harness_measures_subprocess_workers():
    report = run_benchmark(
        workers=2, total_steps=300, warmup_steps=20, circuit=CIRCUIT, vec="subproc"
    )

    assert report["workers"] == 2
    assert report["steps_s_aggregate"] > 0
