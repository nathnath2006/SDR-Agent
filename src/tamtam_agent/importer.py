"""Import d'un export : aperçu des feuilles, statistiques et regroupements à valider.

Chaque import vit dans data/imports/<id>/ : le fichier source, son inspection
(inspection.json) et la validation du SDR (validation.json).
"""

from __future__ import annotations

import json
import math
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import config
from .clean import country_check, suggest_groups
from .load import load_case_data

MAX_PREVIEW_ROWS = 2000


def create(imports_dir: Path, filename: str, content: bytes) -> str:
    import_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    folder = imports_dir / import_id
    folder.mkdir(parents=True)
    (folder / "source.xlsx").write_bytes(content)
    (folder / "meta.json").write_text(json.dumps({"id": import_id, "fichier": filename,
                                                  "importe_le": datetime.now().isoformat(timespec="seconds")}))
    try:
        inspection = inspect(folder / "source.xlsx")
    except Exception as exc:   # fichier illisible ou au mauvais format : on ne garde rien
        shutil.rmtree(folder)
        raise ValueError(str(exc) or type(exc).__name__) from exc
    (folder / "inspection.json").write_text(json.dumps(inspection, ensure_ascii=False, default=str))
    return import_id


def inspect(path: Path) -> dict:
    """Ce que le SDR doit voir avant de lancer l'analyse."""
    data = load_case_data(path)   # lève une erreur claire si un onglet ou une colonne manque
    raw = pd.read_excel(path, sheet_name=None)
    p, ev = data.prospects, data.events

    countries = [country_check(n, w, c) for n, w, c in zip(p["Name"], p["Website"], p["Country"])]
    p_country = pd.Series([c["country"] for c in countries], index=p.index)
    region = p_country.map(_region)

    by_detail = (ev.groupby(["Type", "Detail"]).size().reset_index(name="n")
                 .sort_values(["Type", "n"], ascending=[True, False]))
    # Tous les mois de la période, y compris ceux sans événement : un trou se voit.
    periods = ev["Date"].dt.to_period("M")
    all_months = pd.period_range(periods.min(), periods.max(), freq="M") if len(ev) else []
    months = periods.value_counts().reindex(all_months, fill_value=0)
    months.index = months.index.astype(str)

    return {
        "feuilles": [_sheet_preview(name, df) for name, df in raw.items()],
        "stats": {
            "prospects": len(p),
            "evenements": len(ev),
            "comptes_avec_evenement": int(ev.loc[ev["AccountId"].isin(p["Id"]), "AccountId"].nunique()),
            "periode": {"debut": ev["Date"].min().date().isoformat(), "fin": ev["Date"].max().date().isoformat()},
            "evenements_par_type": _counts(ev["Type"]),
            "evenements_par_detail": [{"type": r.Type, "detail": r.Detail, "n": int(r.n)} for r in by_detail.itertuples()],
            "evenements_par_mois": [{"mois": m, "n": int(n)} for m, n in months.items()],
            "comptes_par_region": _counts(region),
            "comptes_par_pays": _counts(p_country.fillna("inconnu"), top=15),
            "comptes_par_secteur": _counts(p["Industry"].fillna("non renseigné"), top=12),
            "comptes_par_taille": _counts(p["CompanySize"].fillna("non renseignée"), order=list(config.SIZE_BANDS)),
        },
        "qualite": {
            "regroupements": suggest_groups(p),
            "pays": [{"id": int(i), "nom": n, "declare": d if isinstance(d, str) else "", "probable": c["country"] or "",
                      "note": c["country_note"]}
                     for i, n, d, c in zip(p["Id"], p["Name"], p["Country"], countries) if c["country_flag"] != "ok"],
            "champs_vides": {col: int(p[col].isna().sum()) for col in ("Country", "Industry", "CompanySize", "Website")},
            "evenements_orphelins": int(len(data.orphan_events)),
            "ignore": [
                {"feuille": name, "colonnes": [str(c) for c in raw[name].columns if str(c).startswith("Unnamed")],
                 "lignes": int(len(raw[name].dropna(how="all")) - kept)}
                for name, kept in (("tamtam_prospects", len(p)), ("events", len(ev)))
                if any(str(c).startswith("Unnamed") for c in raw[name].columns) or len(raw[name].dropna(how="all")) > kept
            ],
        },
    }


def _region(country: object) -> str:
    if not isinstance(country, str) or not country:
        return "Inconnue"
    if country in config.GEO_PRIORITY_1:
        return "France et DACH"
    if country in config.EUROPE:
        return "Reste de l'Europe"
    if country in config.US:
        return "États-Unis"
    return "Hors zone"


def _counts(series: pd.Series, top: int | None = None, order: list[str] | None = None) -> list[dict]:
    counts = series.value_counts()
    if order:
        counts = counts.reindex([o for o in order if o in counts.index] + [i for i in counts.index if i not in order])
    items = [{"label": str(k), "n": int(v)} for k, v in counts.items()]
    if top and len(items) > top:
        items = items[:top] + [{"label": "autres", "n": sum(i["n"] for i in items[top:])}]
    return items


def _sheet_preview(name: str, df: pd.DataFrame) -> dict:
    def cell(v):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return None
        if isinstance(v, (pd.Timestamp, datetime)):
            return v.isoformat()
        if isinstance(v, float) and v.is_integer():
            return int(v)
        return v if isinstance(v, (int, float, str, bool)) else str(v)

    df = df.dropna(how="all")
    return {"nom": name, "lignes": len(df), "colonnes": [str(c) for c in df.columns],
            "valeurs": [[cell(v) for v in row] for row in df.head(MAX_PREVIEW_ROWS).itertuples(index=False)]}


def save_validation(folder: Path, decisions: dict[str, bool]) -> dict:
    validation = {"decisions": decisions, "valide_le": datetime.now().isoformat(timespec="seconds")}
    (folder / "validation.json").write_text(json.dumps(validation, ensure_ascii=False))
    return validation


def summary(folder: Path) -> dict:
    meta = json.loads((folder / "meta.json").read_text())
    validation = folder / "validation.json"
    meta["valide"] = validation.exists()
    if validation.exists():
        meta["validation"] = json.loads(validation.read_text())
    return meta
