"""Typage des événements (D4 à D8) : déclencheur, amplificateur, contexte, bruit.

Les règles ci-dessous décident seules : même export, même classement. Le LLM,
s'il est configuré, ne fait que traduire chaque événement en français.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import pandas as pd

from . import config
from .llm import LLMClient

T, A, C, N, CLIENT = (config.ROLE_TRIGGER, config.ROLE_AMPLIFIER, config.ROLE_CONTEXT,
                      config.ROLE_NOISE, config.ROLE_CLIENT)


@dataclass(frozen=True)
class Rule:
    types: tuple[str, ...] | None   # None = tous les types
    pattern: str
    role: str
    nature: str
    reason: str


# Ordre important : la première règle qui correspond s'applique.
RULES: tuple[Rule, ...] = (
    Rule(None, r"mirakl", CLIENT, "",
         "Mirakl déjà en place : client à développer, pas prospect (D6)"),
    Rule(("acquisition",), r"online retailer|assortment|e-?commerce", T, "acquisition",
         "acquisition pour élargir l'assortiment en ligne (D4)"),
    Rule(("acquisition",), r".", A, "", "acquisition sans lien e-commerce explicite"),
    Rule(None, r"third-party sellers|open .* to .*sellers", T, "ouverture_vendeurs",
         "annonce d'ouverture du site à des vendeurs tiers (D4)"),
    Rule(None, r"drop-?ship", T, "dropship", "lancement de drop-ship avec des marques partenaires (D4)"),
    Rule(("job_posting",), r"marketplace|third-party assortment|seller onboarding", T, "recrutement",
         "poste dédié à la marketplace ou à l'assortiment tiers (D4, D7)"),
    Rule(("job_posting",), r"e-?commerce director|digital commerce|e-?commerce strategist|head of e-?commerce",
         T, "recrutement",
         "recrutement du dirigeant e-commerce : l'outil se choisit avant l'annonce (D5)"),
    Rule(("job_posting",), r"sales roles|\bsdr\b|account executive", C, "",
         "postes commerciaux : croissance des ventes, pas intention marketplace (D7)"),
    Rule(("job_posting",), r"data|engineer|developer|marketing manager|head of|director|manager", A, "",
         "poste data / dev / managérial sans e-commerce explicite (D8)"),
    Rule(("job_posting",), r".", C, "", "poste opérationnel, pèse peu (D7)"),
    Rule(("funding_round",), r".", A, "", "financement : budget et pression de croissance, jamais déclencheur seul (D2)"),
    Rule(("leadership_change",), r"\bceo\b", A, "", "nouveau CEO : fenêtre de décision (D4)"),
    Rule(("leadership_change",), r".", C, "", "changement hors direction générale (CFO…) : contexte (D4)"),
    Rule(("linkedin_growth",), r"store|production|retail roles", C, "",
         "croissance surtout magasin ou production : opérationnelle, pas digitale (D4)"),
    Rule(("linkedin_growth",), r".", A, "", "croissance des effectifs (D4)"),
    Rule(("tech_stack",), r"vtex", C, "",
         "concurrent détecté (VTEX marketplace) : angle de remplacement, ancienneté inconnue (D6)"),
    Rule(("tech_stack",), r".", C, "",
         "plateforme e-commerce sans marketplace native : base technique, angle d'intégration (D6)"),
    Rule(None, r".", N, "", "actualité sans lien avec une intention marketplace"),
)


def classify_by_rules(event_type: str, detail: str) -> dict:
    text = f"{detail or ''}".lower()
    for i, rule in enumerate(RULES):
        if rule.types is not None and event_type not in rule.types:
            continue
        if re.search(rule.pattern, text):
            return {"role": rule.role, "nature": rule.nature, "raison": rule.reason,
                    "confiance": "haute" if rule.role != N else "moyenne", "regle": f"R{i + 1:02d}"}
    raise AssertionError("la dernière règle couvre tous les cas")


LABEL_SCHEMA = {
    "type": "object",
    "properties": {
        "labels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "libelle": {"type": "string"}},
                "required": ["id", "libelle"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["labels"],
    "additionalProperties": False,
}

LABEL_SYSTEM = """Traduis en français chaque événement détecté sur une entreprise.
"libelle" : le fait lui-même, court (12 mots au plus), sans interprétation ni ajout. Garde les intitulés de poste en anglais."""

BATCH_SIZE = 40


def classify_events(events: pd.DataFrame, llm: LLMClient | None) -> pd.DataFrame:
    """Ajoute role, nature, raison, confiance, regle et libelle (français si LLM) à chaque événement."""
    ev = events.copy()
    rules = [classify_by_rules(t, d) for t, d in zip(ev["Type"], ev["Detail"])]
    for key in ("role", "nature", "raison", "confiance", "regle"):
        ev[key] = [r[key] for r in rules]
    ev["libelle"] = ev["Detail"]   # texte d'origine tant qu'il n'est pas traduit
    if llm is None:
        return ev

    details = sorted(set(ev["Detail"].dropna()))
    labels: dict[str, str] = {}
    for start in range(0, len(details), BATCH_SIZE):
        batch = [{"id": str(i), "texte": d} for i, d in enumerate(details[start:start + BATCH_SIZE], start=start)]
        result = llm.json(LABEL_SYSTEM, json.dumps(batch, ensure_ascii=False, indent=1), LABEL_SCHEMA,
                          task="translate_events", effort="low")
        for item in result.get("labels", []):
            if item.get("id", "").isdigit() and int(item["id"]) < len(details) and item.get("libelle"):
                labels[details[int(item["id"])]] = item["libelle"]
    ev["libelle"] = [labels.get(d, d) for d in ev["Detail"]]
    return ev
