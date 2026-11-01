"""API : import, validation, analyse hors ligne, historique, paramètres."""

import io
import shutil
import time
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "mirakl_case_data.xlsx"


@pytest.fixture
def client(tmp_path, monkeypatch):
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "TAMTAM_LLM_PROVIDER", "APP_PASSWORD",
                "TAMTAM_STORE"):
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
    export = f"/api/runs/{job['run']}/export"
    full = client.get(export)
    assert full.status_code == 200 and full.headers["content-disposition"].endswith('.xlsx"')
    sheets = pd.read_excel(io.BytesIO(full.content), sheet_name=None)
    assert list(sheets) == ["Top 20", "TAM priorisé", "Hors cible à surveiller", "Clients Mirakl", "Limites"]
    assert len(sheets["Top 20"]) == 20 and sheets["Top 20"]["rang top 20"].tolist() == list(range(1, 21))
    top_csv = client.get(export, params={"liste": "top", "format": "csv"})
    assert top_csv.content.startswith("\ufeff".encode()) and top_csv.content.decode("utf-8-sig").startswith("rang;compte;")
    assert client.get(export, params={"format": "csv"}).status_code == 400
    history = client.get("/api/runs").json()
    assert [h["run_id"] for h in history] == [job["run"]]


def test_user_key_used_but_never_written(client, tmp_path, monkeypatch):
    from tamtam_agent import agent
    from test_memory_and_llm import FakeLLM
    seen = {}

    def fake_get_llm(provider, cache_dir=None, api_key=None, model=None):
        seen.update(provider=provider, api_key=api_key, model=model)
        return FakeLLM()

    monkeypatch.setattr(agent, "get_llm", fake_get_llm)
    imp = client.post("/api/imports?name=export.xlsx", content=SOURCE.read_bytes()).json()
    client.post(f"/api/imports/{imp['id']}/validate", json={"decisions": {}})
    key = "user-secret-key-123456"
    body = {"web": False, "llm": {"provider": "gemini", "api_key": key, "model": "gemini-test"}}
    assert client.post(f"/api/imports/{imp['id']}/analyze", json=body).status_code == 202
    job = _wait(client)
    assert job["state"] == "done", job
    assert seen == {"provider": "gemini", "api_key": key, "model": "gemini-test"}
    assert key not in str(job)
    written = [f for f in tmp_path.rglob("*") if f.is_file() and f.suffix != ".xlsx"]
    assert written and not any(key in f.read_text(errors="ignore") for f in written)


def test_config_exposes_default_models_only(client):
    cfg = client.get("/api/config").json()
    assert set(cfg) == {"models", "rules"} and set(cfg["models"]) == {"gemini", "anthropic"}


def test_rejects_bad_input(client):
    assert client.post("/api/imports?name=evil.sh", content=b"x").status_code == 400
    assert client.post("/api/imports?name=bad.xlsx", content=b"pas un excel").status_code == 400
    assert client.get("/api/imports").json() == []
    assert client.get("/api/runs/not-a-run").status_code == 404
    assert client.get("/api/imports/../../etc").status_code == 404


def test_password_protects_api(tmp_path, monkeypatch):
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "TAMTAM_LLM_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("TAMTAM_ROOT", str(tmp_path))
    monkeypatch.setenv("TAMTAM_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("APP_PASSWORD", "s3cret")
    import importlib
    from tamtam_agent import api
    importlib.reload(api)
    client = TestClient(api.app)

    assert client.get("/api/session").json() == {"protege": True, "connecte": False}
    assert client.get("/api/config").status_code == 401
    assert client.post("/api/login", json={"password": "faux"}).status_code == 401
    assert client.post("/api/login", json={"password": "s3cret"}).status_code == 200
    assert client.get("/api/config").status_code == 200
    assert api.IMPORTS_DIR == (tmp_path / "store" / "data" / "imports").resolve()
