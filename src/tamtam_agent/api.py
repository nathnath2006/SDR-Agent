"""API HTTP de l'interface (et service du front compilé).

    tamtam-agent serve        # http://localhost:8000

Parcours : importer un export -> le valider (regroupements) -> lancer l'analyse
-> consulter le Top 20 et l'historique. Dossiers relatifs à TAMTAM_ROOT
(par défaut : le dossier courant).
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from collections import deque
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agent, config, importer, outputs, settings
from .llm import LLMError, get_llm

ROOT = Path(os.getenv("TAMTAM_ROOT", Path.cwd())).resolve()
IMPORTS_DIR = ROOT / "data" / "imports"
OUT_DIR = ROOT / "outputs"
RUNS_DIR = OUT_DIR / "runs"
CACHE_DIR = ROOT / ".cache" / "llm"
WEB_DIST = ROOT / "web" / "dist"
ID_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}$")
DOWNLOADS = {
    "top20.md": "text/markdown",
    "tam_priorise.xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "tam_priorise.csv": "text/csv",
    "explications.jsonl": "application/jsonl",
    "limites_des_donnees.md": "text/markdown",
    "llm_log.jsonl": "application/jsonl",
}

app = FastAPI(title="tamtam-agent")


@app.get("/api/config")
def get_config() -> dict:
    return {
        "llm": settings.describe(),
        "rules": {"recent_days": config.WINDOW_RECENT_DAYS, "max_days": config.WINDOW_MAX_DAYS,
                  "size_min": config.SIZE_MIN, "size_max": config.SIZE_MAX, "top_n": config.TOP_N},
    }


# --- Import et validation ----------------------------------------------------------
@app.get("/api/imports")
def list_imports() -> list[dict]:
    if not IMPORTS_DIR.exists():
        return []
    folders = sorted((p for p in IMPORTS_DIR.iterdir() if ID_PATTERN.match(p.name)), reverse=True)
    return [importer.summary(p) for p in folders if (p / "meta.json").exists()]


@app.post("/api/imports", status_code=201)
async def create_import(request: Request, name: str) -> dict:
    filename = Path(name).name
    if not filename.lower().endswith(".xlsx") or filename.startswith("~$"):
        raise HTTPException(400, "un fichier .xlsx est attendu")
    try:
        import_id = importer.create(IMPORTS_DIR, filename, await request.body())
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, f"export illisible : {exc}") from exc
    return get_import(import_id)


@app.get("/api/imports/{import_id}")
def get_import(import_id: str) -> dict:
    folder = _import_dir(import_id)
    return importer.summary(folder) | {"inspection": json.loads((folder / "inspection.json").read_text())}


class Validation(BaseModel):
    decisions: dict[str, bool]   # id de regroupement -> fusionner ?


@app.post("/api/imports/{import_id}/validate")
def validate_import(import_id: str, body: Validation) -> dict:
    folder = _import_dir(import_id)
    importer.save_validation(folder, body.decisions)
    return importer.summary(folder)


def _import_dir(import_id: str) -> Path:
    folder = IMPORTS_DIR / import_id
    if not ID_PATTERN.match(import_id) or not (folder / "meta.json").exists():
        raise HTTPException(404, "import introuvable")
    return folder


# --- Analyse (une à la fois, en arrière-plan) -------------------------------------------
class AnalyzeRequest(BaseModel):
    web: bool = True


class _Job:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.state, self.message, self.run, self.import_id = "idle", "", None, None
        self.logs: deque[str] = deque(maxlen=300)
        self.started: str | None = None

    def as_dict(self) -> dict:
        return {"state": self.state, "message": self.message, "run": self.run, "import_id": self.import_id,
                "logs": list(self.logs), "started": self.started}


JOB = _Job()


class _JobLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        JOB.logs.append(f"{datetime.now():%H:%M:%S} {record.getMessage()}")


@app.get("/api/job")
def get_job() -> dict:
    return JOB.as_dict()


@app.post("/api/imports/{import_id}/analyze", status_code=202)
def analyze(import_id: str, req: AnalyzeRequest) -> dict:
    folder = _import_dir(import_id)
    validation = folder / "validation.json"
    if not validation.exists():
        raise HTTPException(409, "valide d'abord les données (regroupements) dans l'onglet Import")
    decisions = json.loads(validation.read_text())["decisions"]
    with JOB.lock:
        if JOB.state == "running":
            raise HTTPException(409, "une analyse est déjà en cours")
        JOB.state, JOB.message, JOB.run, JOB.import_id = "running", "Analyse en cours", None, import_id
        JOB.logs.clear()
        JOB.started = datetime.now().isoformat(timespec="seconds")
    threading.Thread(target=_execute, args=(folder, decisions, req.web), daemon=True).start()
    return JOB.as_dict()


def _execute(folder: Path, decisions: dict[str, bool], web: bool) -> None:
    logger = logging.getLogger("tamtam_agent")
    handler = _JobLogHandler()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        meta = json.loads((folder / "meta.json").read_text())
        result = agent.run(folder / "source.xlsx", OUT_DIR, web=web, cache_dir=CACHE_DIR,
                           group_decisions=decisions)
        result.source = meta["fichier"]
        outputs.write_all(result, OUT_DIR)
        (RUNS_DIR / result.run_id / "import.json").write_text(json.dumps({"import_id": folder.name, **meta}))
        JOB.run, JOB.state = result.run_id, "done"
        JOB.message = f"Top {len(result.top)} prêt · LLM : {result.llm_label}"
    except Exception as exc:   # renvoyée telle quelle à l'interface
        JOB.state, JOB.message = "error", f"{type(exc).__name__} : {exc}"
        logger.exception("Analyse en échec")
    finally:
        logger.removeHandler(handler)


# --- Résultats et historique ------------------------------------------------------------
def _run_ids() -> list[str]:
    if not RUNS_DIR.exists():
        return []
    return sorted((p.name for p in RUNS_DIR.iterdir() if ID_PATTERN.match(p.name) and (p / "meta.json").exists()),
                  reverse=True)


@app.get("/api/runs")
def list_runs() -> list[dict]:
    """Historique : chaque analyse, et ce qui a changé dans le Top par rapport à la précédente."""
    metas = [json.loads((RUNS_DIR / r / "meta.json").read_text()) for r in _run_ids()]
    names = {}
    for r in _run_ids():
        for line in (RUNS_DIR / r / "explications.jsonl").read_text().splitlines():
            a = json.loads(line)
            if a.get("rang_top"):
                names[a["groupe_id"]] = a["compte"]
    for meta, previous in zip(metas, metas[1:] + [None]):
        top = meta.get("top_ids", [])
        before = previous.get("top_ids", []) if previous else []
        meta["entres"] = [names.get(i, str(i)) for i in top if previous and i not in before]
        meta["sortis_top"] = [names.get(i, str(i)) for i in before if i not in top]
        meta.pop("limites", None)
    return metas


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    run_dir = _run_dir(run_id)
    accounts = [json.loads(line) for line in (run_dir / "explications.jsonl").read_text().splitlines() if line]
    for rank, a in enumerate(accounts, start=1):   # le fichier est déjà trié comme le TAM
        a["rang"] = rank
    meta = json.loads((run_dir / "meta.json").read_text())
    files = [name for name in DOWNLOADS if (run_dir / name).exists()]
    return {"meta": meta, "accounts": accounts, "files": files}


@app.get("/api/runs/{run_id}/files/{name}")
def download(run_id: str, name: str) -> FileResponse:
    path = _run_dir(run_id) / name
    if name not in DOWNLOADS or not path.exists():
        raise HTTPException(404, "fichier inconnu")
    return FileResponse(path, media_type=DOWNLOADS[name], filename=name)


@app.get("/api/memory")
def download_memory() -> FileResponse:
    path = OUT_DIR / "memoire.csv"
    if not path.exists():
        raise HTTPException(404, "pas encore de mémoire")
    return FileResponse(path, media_type="text/csv", filename="memoire.csv")


def _run_dir(run_id: str) -> Path:
    if not ID_PATTERN.match(run_id) or not (RUNS_DIR / run_id / "explications.jsonl").exists():
        raise HTTPException(404, "analyse introuvable")
    return RUNS_DIR / run_id


# --- Paramètres LLM ---------------------------------------------------------------------
class SettingsRequest(BaseModel):
    provider: str
    api_key: str | None = None
    model: str | None = None


@app.post("/api/settings")
def save_settings(req: SettingsRequest) -> dict:
    try:
        settings.save(ROOT / ".env", req.provider, req.api_key, req.model)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return settings.describe()


@app.post("/api/settings/test")
def test_settings() -> dict:
    """Appel minimal au fournisseur actif, pour vérifier la clé."""
    llm = get_llm("auto")
    if llm is None:
        raise HTTPException(400, "aucune clé enregistrée")
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"],
              "additionalProperties": False}
    try:
        llm.json("Réponds au format demandé.", 'Renvoie {"ok": true}.', schema, task="test", effort="low")
    except LLMError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "provider": llm.provider, "model": llm.model}


# --- Front compilé (web/dist), servi à la racine --------------------------------------
if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
