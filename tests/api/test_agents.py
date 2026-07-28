"""GET /agents once both triplets are baked (F15, F-24): the registry lists every
model this image can serve — the frozen 2026 headline and the era-matched 2024
model — each carrying its own version, its own config hash and the fidelity badge
read from its own surrogate's fidelity.json, never the headline's (F-23, E-15).

The models root is faked the way tests/serve/test_model_registry.py fakes it:
hand-written manifests under MODELS_DIR, no checkpoint ever loaded.
"""

import json

import pytest

# stand-in versions, deliberately not the repo's real ones: an implementation that
# ignored MODELS_DIR and read the committed models/ would fail on these strings
HEADLINE_VERSION = "senna-ppo-feedfacecafe-C-00000064"
ERA2024_VERSION = "senna-ppo-1187ab0c9d4e-C-00204800"


def _bake(models_dir, name, model_version, *, era=None, pit_top1, mode_top1):
    triplet = models_dir / name
    triplet.mkdir(parents=True)
    manifest = {"model_version": model_version,
                "fingerprint": model_version.split("-")[2], "stage": "C"}
    if era:
        manifest["era"] = era
    (triplet / "manifest.json").write_text(json.dumps(manifest))

    surrogate = models_dir / "explain" / model_version
    surrogate.mkdir(parents=True)
    (surrogate / "fidelity.json").write_text(json.dumps({
        "model_version": model_version,
        "heads": {"pit": {"top1": pit_top1}, "mode": {"top1": mode_top1}},
    }))


def test_agents_route_lists_both_models(client, tmp_path, monkeypatch):
    root = tmp_path / "models"
    _bake(root, "headline", HEADLINE_VERSION, pit_top1=0.91, mode_top1=0.88)
    _bake(root, "era2024", ERA2024_VERSION, era="2024", pit_top1=0.83, mode_top1=0.79)
    monkeypatch.setenv("MODELS_DIR", str(root))

    agents = client.get("/api/v1/agents").json()
    by_version = {agent["version"]: agent for agent in agents}

    assert set(by_version) == {HEADLINE_VERSION, ERA2024_VERSION}
    assert by_version[HEADLINE_VERSION]["config_hash"] == "feedfacecafe"
    assert by_version[ERA2024_VERSION]["config_hash"] == "1187ab0c9d4e"
    # each badge comes from that model's own surrogate artifacts
    assert by_version[HEADLINE_VERSION]["fidelity"]["pit"] == pytest.approx(0.91)
    assert by_version[ERA2024_VERSION]["fidelity"]["pit"] == pytest.approx(0.83)
    assert by_version[ERA2024_VERSION]["fidelity"]["mode"] == pytest.approx(0.79)
