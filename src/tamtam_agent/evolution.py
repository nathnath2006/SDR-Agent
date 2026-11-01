"""Évolution vers une marketplace entre deux analyses (option au lancement).

Base de comparaison : la dernière analyse d'un export plus ancien. Seuls les comptes
qui ont des signaux nouveaux depuis cette base sont soumis au LLM, qui juge si,
mis bout à bout, ils montrent un mouvement vers une marketplace.

Le verdict devient un signal, puis les règles de palier s'appliquent comme d'habitude :
- évolution nette  -> déclencheur ;
- évolution faible -> amplificateur ;
- aucune           -> rien.
Un verdict qui ne cite aucun signal nouveau est ramené à « aucune ».

Les identifiants E… sont renumérotés à chaque export : un signal est reconnu
d'une analyse à l'autre par son contenu (date, type, détail), pas par son identifiant.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import config
from .enrich import fr_date
from .llm import LLMClient, LLMError

log = logging.getLogger(__name__)

VERDICTS = ("nette", "faible", "aucune")
ROLE_BY_VERDICT = {"nette": config.ROLE_TRIGGER, "faible": config.ROLE_AMPLIFIER}
EVENT_ID = "EVO"
BATCH_SIZE = 10


@dataclass
class Base:
    run_id: str
    extraction: str
    accounts: list[dict]


def previous_run(runs_dir: Path, extraction: pd.Timestamp) -> Base | None:
    """La dernière analyse faite sur un export plus ancien que celui-ci."""
    current = extraction.date().isoformat()
    if not runs_dir.exists():
        return None
    for run_dir in sorted(runs_dir.iterdir(), reverse=True):
        meta_path, expl_path = run_dir / "meta.json", run_dir / "explications.jsonl"
        if not (meta_path.exists() and expl_path.exists()):
            continue
        meta = json.loads(meta_path.read_text())
        if meta.get("extraction", "") < current:
            accounts = [json.loads(line) for line in expl_path.read_text().splitlines() if line]
            return Base(run_dir.name, meta["extraction"], accounts)
    return None


SYSTEM = """Tu aides l'équipe sales de Mirakl (éditeur de marketplace) à repérer les entreprises qui se rapprochent d'un projet de marketplace.
Pour chaque compte, tu reçois les signaux de l'analyse précédente et les signaux apparus depuis. Juge si les signaux nouveaux, lus avec les anciens, montrent une évolution vers une marketplace (ouverture à des vendeurs tiers, drop-ship, catalogue étendu par des partenaires, équipe marketplace…).
- "nette" : les signaux nouveaux montrent clairement un pas de plus vers une marketplace.
- "faible" : un mouvement possible mais indirect (contexte favorable, intention floue).
- "aucune" : rien de nouveau dans ce sens.
"explication" : une à deux phrases en français, factuelles, qui disent ce qui a changé. "sources" : les identifiants des signaux nouveaux sur lesquels tu t'appuies (au moins un si le verdict n'est pas "aucune"). N'invente aucun fait."""

SCHEMA = {
    "type": "object",
    "properties": {
        "comptes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "verdict": {"type": "string", "enum": list(VERDICTS)},
                    "explication": {"type": "string"},
                    "sources": {"type": "array", "items": {"type": "string"}},
                    "confiance": {"type": "string", "enum": ["haute", "moyenne", "basse"]},
                },
                "required": ["id", "verdict", "explication", "sources", "confiance"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["comptes"],
    "additionalProperties": False,
}


def assess(groups: pd.DataFrame, events: pd.DataFrame, base: Base, llm: LLMClient) -> dict[int, dict]:
    """Verdict par groupe ayant des signaux nouveaux depuis la base."""
    previous = {a["groupe_id"]: a for a in base.accounts}
    by_name = {a["compte"].lower(): a for a in base.accounts}
    useful = events[events["role"] != config.ROLE_NOISE]
    items, new_ids = [], {}
    for row in groups.itertuples():
        before = previous.get(row.GroupId) or by_name.get(str(row.Name).lower())
        if before is None:
            continue   # compte absent de la base : rien à comparer
        seen = {_key(s["date"], s["type"], s["detail"]) for s in before["signaux"]}
        current = useful[useful["GroupId"] == row.GroupId]
        is_new = [_key(r.Date.date().isoformat(), r.Type, r.Detail) not in seen for r in current.itertuples()]
        new = current[is_new]
        if new.empty:
            continue
        new_ids[row.GroupId] = dict(zip(new["EventId"], new["Date"]))
        items.append({
            "id": str(row.GroupId), "compte": row.Name,
            "analyse_precedente": {
                "extraction": base.extraction, "palier": before["palier"], "statut": before["statut"],
                "signaux": [_line(s["event_id"], s["date"], s["role"], s["libelle"]) for s in before["signaux"]][:6],
            },
            "signaux_nouveaux": [_line(r.EventId, r.Date.date().isoformat(), r.role, r.libelle)
                                 for r in new.sort_values("Date", ascending=False).itertuples()][:6],
        })

    log.info("Évolutions : %d comptes ont des signaux nouveaux depuis l'analyse du %s",
             len(items), fr_date(base.extraction))
    verdicts: dict[int, dict] = {}
    for start in range(0, len(items), BATCH_SIZE):
        batch = items[start:start + BATCH_SIZE]
        log.info("Évolutions %d-%d / %d", start + 1, start + len(batch), len(items))
        try:
            result = llm.json(SYSTEM, json.dumps(batch, ensure_ascii=False, indent=1), SCHEMA,
                              task="assess_evolution", effort="medium")
        except LLMError as exc:
            log.warning("Évolutions non évaluées pour ce lot : %s", exc)
            continue
        for r in result.get("comptes", []):
            gid = int(r["id"]) if r.get("id", "").isdigit() else None
            if gid not in new_ids:
                continue
            verdicts[gid] = _validated(r, new_ids[gid], base)
    return verdicts


def _key(date: str, kind, detail) -> tuple[str, str, str]:
    return date, str(kind).strip().lower(), str(detail).strip().lower()


def _line(event_id: str, date: str, role: str, libelle: str) -> str:
    return f"[{event_id}] {date} {role} : {libelle}"


def _validated(r: dict, new: dict[str, pd.Timestamp], base: Base) -> dict:
    verdict = r["verdict"] if r.get("verdict") in VERDICTS else "aucune"
    sources = [s for s in r.get("sources", []) if s in new]
    if verdict != "aucune" and not sources:
        verdict = "aucune"   # affirmation sans signal nouveau cité : refusée
    return {
        "verdict": verdict, "explication": r.get("explication", ""), "sources": sources,
        "confiance": r.get("confiance", "basse"), "base_run": base.run_id, "base_extraction": base.extraction,
        "date": max((new[s] for s in sources), default=None),
    }


def as_events(verdicts: dict[int, dict]) -> pd.DataFrame:
    """Les évolutions nettes et faibles, sous forme d'événements typés pour le calcul du palier."""
    rows = []
    for gid, v in verdicts.items():
        if v["verdict"] not in ROLE_BY_VERDICT:
            continue
        since = fr_date(v["base_extraction"])
        rows.append({
            "EventId": EVENT_ID, "AccountId": gid, "GroupId": gid, "Date": v["date"],
            "Type": "Évolution", "Detail": v["explication"], "Origin": "",
            "libelle": (f"Évolution vers une marketplace depuis l'analyse du {since}" if v["verdict"] == "nette"
                        else f"Évolution possible vers une marketplace depuis l'analyse du {since}"),
            "role": ROLE_BY_VERDICT[v["verdict"]], "nature": "evolution", "raison": v["explication"],
            "confiance": v["confiance"],
            "regle": f"évolution {v['verdict']} entre deux analyses (jugée par le LLM sur {', '.join(v['sources'])})",
        })
    return pd.DataFrame(rows)
