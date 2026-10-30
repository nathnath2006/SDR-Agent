"""API : import, validation, analyse hors ligne, historique, paramètres."""

import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "mirakl_case_data.xlsx"


@pytest.fixture
def client(tmp_path, monkeypatch):
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "TAMTAM_LLM_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("TAMTAM_ROOT", str(tmp_path))
    import importlib
    from tamtam_agent import api
    importlib.reload(api)
    return TestClient(api.app)

from conftest import DATA as _DATA

pytestmark = pytest.mark.skipif(not _DATA.exists(), reason="export du cas non versionné")


def _wait(client):
    for _ in range(200):
        job = client.get("/api/job").json()
        if job["state"] != "running":
            return job
        time.sleep(0.1)
    raise AssertionError("analyse trop longue")


def test_import_validate_analyze_history(client):
    imp = client.post("/api/imports?name=export.xlsx", content=SOURCE.read_bytes()).json()
    stats = imp["inspection"]["stats"]
    assert stats["prospects"] == 466 and stats["evenements"] == 121
    groups = imp["inspection"]["qualite"]["regroupements"]
    assert len(groups) == 7 and not imp["valide"]

    # Analyse refusée tant que les données ne sont pas validées.
    assert client.post(f"/api/imports/{imp['id']}/analyze", json={"web": False}).status_code == 409
    decisions = {g["id"]: g["type"] == "doublon" for g in groups}
    assert client.post(f"/api/imports/{imp['id']}/validate", json={"decisions": decisions}).json()["valide"]

    assert client.post(f"/api/imports/{imp['id']}/analyze", json={"web": False}).status_code == 202
    job = _wait(client)
    assert job["state"] == "done", job
    run = client.get(f"/api/runs/{job['run']}").json()
    assert run["meta"]["top"] == 20 and run["meta"]["source"] == "export.xlsx"
    assert client.get(f"/api/runs/{job['run']}/files/top20.md").status_code == 200
    history = client.get("/api/runs").json()
    assert [h["run_id"] for h in history] == [job["run"]]


def test_settings_written_to_env(client, tmp_path):
    (tmp_path / ".env").write_text("OTHER=1\n# GEMINI_API_KEY=\n")
    out = client.post("/api/settings", json={"provider": "gemini", "api_key": "AIzaTESTKEY1234567890"}).json()
    assert out["provider"] == "gemini" and out["providers"]["gemini"]["key_hint"] == "AIza…7890"
    env = (tmp_path / ".env").read_text()
    assert "OTHER=1" in env and "GEMINI_API_KEY=AIzaTESTKEY1234567890" in env and "TAMTAM_LLM_PROVIDER=gemini" in env
    assert "AIzaTESTKEY" not in str(client.get("/api/config").json())   # la clé ne ressort jamais


def test_rejects_bad_input(client):
    assert client.post("/api/imports?name=evil.sh", content=b"x").status_code == 400
    assert client.post("/api/imports?name=bad.xlsx", content=b"pas un excel").status_code == 400
    assert client.get("/api/imports").json() == []
    assert client.get("/api/runs/not-a-run").status_code == 404
    assert client.get("/api/imports/../../etc").status_code == 404
