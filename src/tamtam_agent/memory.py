"""Mémoire de l'agent (D14) : une ligne par entreprise, comparée d'une semaine à l'autre."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .tiers import TIER_ORDER

COLUMNS = ["groupe_id", "compte", "date_traitement", "date_extraction", "statut", "palier",
           "commentaire", "statut_precedent", "palier_precedent", "date_extraction_precedente"]


def load(path: Path) -> pd.DataFrame:
    if path.exists():
        return pd.read_csv(path, dtype={"groupe_id": "int64"}).reindex(columns=COLUMNS)
    return pd.DataFrame(columns=COLUMNS)


def compare(current: pd.DataFrame, memory: pd.DataFrame, extraction: str) -> pd.DataFrame:
    """Ajoute `evolution` et `evolution_detail` à la table courante.

    current : colonnes groupe_id, compte, statut, palier, raison.
    Relancer sur la même extraction ne change pas la comparaison (idempotent).
    """
    previous = {}
    for row in memory.itertuples(index=False):
        if row.date_extraction == extraction:
            previous[row.groupe_id] = (row.statut_precedent, row.palier_precedent, row.date_extraction_precedente)
        else:
            previous[row.groupe_id] = (row.statut, row.palier, row.date_extraction)

    evolution, detail = [], []
    for row in current.itertuples(index=False):
        prev = previous.get(row.groupe_id)
        if prev is None or pd.isna(prev[1]):
            evolution.append("nouveau")
            detail.append("première analyse")
            continue
        p_status, p_tier, p_date = prev
        delta = TIER_ORDER[row.palier] - TIER_ORDER.get(p_tier, 4)
        word = "monté" if delta < 0 else "baissé" if delta > 0 else "inchangé"
        if word == "inchangé" and p_status != row.statut:
            word = "statut modifié"
        evolution.append(word)
        detail.append("" if word == "inchangé" else
                      f"{p_tier} → {row.palier}, {p_status} → {row.statut} (extraction du {p_date})")
    return current.assign(evolution=evolution, evolution_detail=detail)


def update(current: pd.DataFrame, memory: pd.DataFrame, extraction: str, run_date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retourne (nouvelle mémoire, comptes sortis de l'export)."""
    old = memory.set_index("groupe_id") if not memory.empty else pd.DataFrame(columns=COLUMNS[1:])
    rows = []
    for row in current.itertuples(index=False):
        prev = old.loc[row.groupe_id] if row.groupe_id in old.index else None
        if prev is not None and prev["date_extraction"] == extraction:
            p_status, p_tier, p_date = prev["statut_precedent"], prev["palier_precedent"], prev["date_extraction_precedente"]
        elif prev is not None:
            p_status, p_tier, p_date = prev["statut"], prev["palier"], prev["date_extraction"]
        else:
            p_status = p_tier = p_date = None
        rows.append({"groupe_id": row.groupe_id, "compte": row.compte, "date_traitement": run_date,
                     "date_extraction": extraction, "statut": row.statut, "palier": row.palier,
                     "commentaire": row.raison, "statut_precedent": p_status,
                     "palier_precedent": p_tier, "date_extraction_precedente": p_date})
    current_ids = set(current["groupe_id"])
    gone = memory[~memory["groupe_id"].isin(current_ids)] if not memory.empty else memory
    new_memory = pd.concat([pd.DataFrame(rows, columns=COLUMNS), gone], ignore_index=True)
    return new_memory, gone
