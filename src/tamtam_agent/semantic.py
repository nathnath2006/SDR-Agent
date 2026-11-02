"""Couche sémantique (mode hybride) : un petit modèle d'embeddings multilingue,
gratuit et local, relit le texte de chaque événement après les règles.

Le modèle compare le texte à des phrases d'exemple par rôle et donne un score
de proximité. Il ne remplace pas les règles, il les corrige dans deux cas :
- promotion : il voit un rôle plus fort que la règle (déclencheur, amplificateur…)
  avec un score d'au moins SEMANTIC_PROMOTE -> le rôle du modèle s'applique ;
- rétrogradation : la règle dit déclencheur, mais le texte est très proche d'un
  contre-exemple de bruit (score d'au moins SEMANTIC_DEMOTE) -> bruit.
Dans les deux cas, le signal est marqué « à relire » dans la fiche.

Garde-fous laissés aux règles seules : « Mirakl » (client), levée de fonds
(amplificateur), technologie en place (VTEX, autres plateformes).
Même modèle, mêmes exemples : mêmes rôles. Les exemples sont génériques : ils
ne recopient pas les événements de l'export.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, signals

log = logging.getLogger(__name__)

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
THRESHOLD = 0.45   # sous ce score, le modèle ne reconnaît rien : bruit
RANK = {config.ROLE_NOISE: 0, config.ROLE_CONTEXT: 1, config.ROLE_AMPLIFIER: 2, config.ROLE_TRIGGER: 3}
T, A, C, N = config.ROLE_TRIGGER, config.ROLE_AMPLIFIER, config.ROLE_CONTEXT, config.ROLE_NOISE

# (rôle, nature, phrase), par type d'événement.
EXAMPLES: dict[str, list[tuple[str, str, str]]] = {
    "job_posting": [
        (T, "recrutement", "Hiring a Head of Marketplace"),
        (T, "recrutement", "Recruiting a Marketplace Manager to launch our marketplace"),
        (T, "recrutement", "Looking for a Category Manager for our third-party seller assortment"),
        (T, "recrutement", "Hiring a specialist to onboard new sellers on our platform"),
        (T, "recrutement", "Hiring an E-commerce Director"),
        (T, "recrutement", "Head of Digital Commerce position open"),
        (T, "recrutement", "Nous recrutons un responsable marketplace"),
        (T, "recrutement", "Recrutement d'un directeur e-commerce"),
        (A, "", "Hiring a Data Engineer"),
        (A, "", "Recruiting software developers for our IT team"),
        (A, "", "Hiring a Marketing Manager"),
        (A, "", "Recrutement d'un ingénieur data"),
        (C, "", "Opening several sales roles"),
        (C, "", "Hiring sales development representatives and account executives"),
        (C, "", "Hiring store staff and cashiers"),
        (C, "", "Recruiting warehouse workers"),
        (C, "", "Hiring a customer service agent"),
        (N, "", "Agency hiring a strategist to help client brands sell on marketplaces"),
        (N, "", "Consulting firm recruiting to support its clients' e-commerce projects"),
        (N, "", "Agence qui recrute pour accompagner ses clients sur les marketplaces"),
    ],
    "news": [
        (T, "ouverture_vendeurs", "Plans to open its website to third-party sellers"),
        (T, "ouverture_vendeurs", "Will launch an online marketplace with external vendors"),
        (T, "ouverture_vendeurs", "Ouvre sa plateforme en ligne à des vendeurs tiers"),
        (T, "dropship", "Launches a drop-ship program with partner brands"),
        (T, "dropship", "Partner brands will ship products directly to customers"),
        (T, "dropship", "Lance le dropshipping avec ses fournisseurs"),
        (N, "", "Sponsors a local sports team"),
        (N, "", "Announces price increases"),
        (N, "", "Publishes its sustainability report"),
        (N, "", "Opens a new warehouse"),
        (N, "", "Opens a new office"),
        (N, "", "Signs a partnership with a supplier"),
        (N, "", "Wins an industry award"),
        (N, "", "Augmente ses prix"),
    ],
    "leadership_change": [
        (A, "", "Appoints a new CEO"),
        (A, "", "New Chief Executive Officer named"),
        (A, "", "Nomination d'un nouveau directeur général"),
        (C, "", "Appoints a new CFO"),
        (C, "", "New Chief Financial Officer"),
        (C, "", "Nouveau directeur financier"),
        (C, "", "New HR director appointed"),
    ],
    "linkedin_growth": [
        (A, "", "Headcount grew 12% in the last six months"),
        (A, "", "Workforce growth in digital and tech teams"),
        (A, "", "Hausse des effectifs de 10 %"),
        (C, "", "Headcount up, mostly store staff"),
        (C, "", "Growth driven by production and retail roles"),
        (C, "", "Hausse des effectifs en magasin"),
    ],
    "acquisition": [
        (T, "acquisition", "Acquires an online retailer to expand its assortment"),
        (T, "acquisition", "Buys an e-commerce company"),
        (T, "acquisition", "Rachète un site e-commerce pour élargir son offre"),
        (A, "", "Acquires a competitor"),
        (A, "", "Acquires a logistics company"),
        (A, "", "Rachète une usine"),
    ],
}


@dataclass
class Verdict:
    role: str
    nature: str
    score: float | None
    exemple: str
    source: str   # « modèle » ou « règle »


def cache_dir() -> Path:
    """Dossier du modèle : TAMTAM_MODELS (intégré à l'image Docker), sinon .cache/models."""
    return Path(os.getenv("TAMTAM_MODELS", Path.cwd() / ".cache" / "models"))


@lru_cache(maxsize=1)
def _model(folder: str):
    from fastembed import TextEmbedding   # import tardif : chargé seulement à la première analyse
    return TextEmbedding(MODEL, cache_dir=folder)


def preload() -> None:
    """Télécharge et charge le modèle (construction de l'image Docker)."""
    _model(str(cache_dir()))


def _embed(texts: list[str]) -> np.ndarray:
    vectors = np.array(list(_model(str(cache_dir())).embed(texts)))
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def classify(items: list[tuple[str, str]]) -> list[Verdict]:
    """items : (type, texte) par événement."""
    out: list[Verdict | None] = [None] * len(items)
    todo: dict[str, list[int]] = {}
    for i, (kind, detail) in enumerate(items):
        text = str(detail or "")
        if re.search("mirakl", text.lower()) or kind not in EXAMPLES:
            r = signals.classify_by_rules(kind, text)
            out[i] = Verdict(r["role"], r["nature"], None, "", "règle")
        elif kind == "funding_round":
            out[i] = Verdict(A, "", None, "", "règle")
        else:
            todo.setdefault(kind, []).append(i)

    for kind, idx in todo.items():
        examples = EXAMPLES[kind]
        ex = _embed([e[2] for e in examples])
        ev = _embed([str(items[i][1]) for i in idx])
        sims = ev @ ex.T
        for row, i in enumerate(idx):
            best = int(sims[row].argmax())
            score = float(sims[row, best])
            role, nature, phrase = examples[best]
            if score < THRESHOLD:
                role, nature = N, ""
            out[i] = Verdict(role, nature, round(score, 2), phrase, "modèle")
    return out  # type: ignore[return-value]


def refine(events: pd.DataFrame) -> pd.DataFrame:
    """Corrige les rôles donnés par les règles (voir le docstring). Ajoute la colonne `reclasse`."""
    ev = events.copy()
    ev["reclasse"] = ""
    verdicts = classify(list(zip(ev["Type"], ev["Detail"])))
    for i, v in zip(ev.index, verdicts):
        if v.source != "modèle":
            continue
        rule_role = ev.at[i, "role"]
        promote = RANK.get(v.role, 0) > RANK.get(rule_role, 0) and v.score >= config.SEMANTIC_PROMOTE
        demote = rule_role == config.ROLE_TRIGGER and v.role == config.ROLE_NOISE and v.score >= config.SEMANTIC_DEMOTE
        if not (promote or demote):
            continue
        ev.at[i, "role"], ev.at[i, "nature"] = v.role, v.nature
        ev.at[i, "raison"] = f"texte proche de « {v.exemple} » (score {v.score:.2f})"
        ev.at[i, "confiance"] = "moyenne"
        ev.at[i, "regle"] = f"modèle ({v.score:.2f})"
        ev.at[i, "reclasse"] = (f"{'promu' if promote else 'rétrogradé'} par le modèle : "
                                f"{rule_role} → {v.role}, proche de « {v.exemple} » ({v.score:.2f})")
    changed = ev[ev["reclasse"] != ""]
    log.info("Modèle sémantique : %d signal(s) reclassé(s) sur %d", len(changed), len(ev))
    return ev
