"""GET /agents against the promoted artifact on disk: version, eval points, fidelity
badge and config hash all come from the baked triplet's own files (F-23), never from a
database row that could drift from what is actually served.
"""

import json

import pytest

from senna import config

HEADLINE = config.REPO_ROOT / "models" / "headline"

pytestmark = pytest.mark.skipif(
    not (HEADLINE / "manifest.json").is_file(),
    reason="needs the baked headline triplet (models/headline)",
)


def test_agents_lists_the_baked_model_with_its_provenance(client):
    manifest = json.loads((HEADLINE / "manifest.json").read_text())
    promotion = json.loads((HEADLINE / "promotion.json").read_text())
    fidelity_path = (
        config.REPO_ROOT / "models" / "explain" / manifest["model_version"] / "fidelity.json"
    )
    if not fidelity_path.is_file():
        pytest.skip("needs the baked surrogate dir (models/explain)")
    fidelity = json.loads(fidelity_path.read_text())

    agents = client.get("/api/v1/agents").json()
    by_version = {agent["version"]: agent for agent in agents}
    served = by_version[manifest["model_version"]]

    assert served["config_hash"] == manifest["fingerprint"]
    assert served["eval_points"] == pytest.approx(promotion["mean_points"])
    assert served["promoted_at"] == promotion["promoted_at"]
    # the F09 badge rides along so the registry can quote honesty per head
    assert served["fidelity"]["pit"] == pytest.approx(fidelity["heads"]["pit"]["top1"])
    assert served["fidelity"]["mode"] == pytest.approx(fidelity["heads"]["mode"]["top1"])
