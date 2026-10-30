"""Explications rédigées par le LLM, en JSON structuré (D3, D5, D13).

Le code décide (statut, palier) ; le LLM explique. Sans clé, aucun texte n'est
rédigé : les décisions restent visibles sous forme de données.

Règle d'or : aucun fait sans source. Chaque fait reçoit un identifiant
(E… = événement, P… = profil Tamtam 2024, W… = vérification web) ; un axe
d'approche qui ne cite pas un identifiant connu est écarté.
"""

from __future__ import annotations

import json
import logging

import pandas as pd

from . import config
from .llm import LLMClient, LLMError, extract_json

log = logging.getLogger(__name__)

_MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
MARKETPLACE_STATES = ("existante", "aucune", "inconnu")
BATCH_SIZE = 25


def fr_date(value) -> str:
    d = pd.Timestamp(value)
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year}"


# --- Vérification web (D5) -----------------------------------------------------
WEB_SYSTEM = """Tu vérifies, pour l'équipe sales de Mirakl, si une entreprise exploite déjà une marketplace.
Cherche sur le web : a-t-elle une marketplace sur son propre site (vendeurs tiers, produits vendus et expédiés par des partenaires), une offre de drop-ship, ou vend-elle via des marketplaces tierces (Amazon, Zalando…) ? Quelle technologie e-commerce ou marketplace est en place, et depuis quand si c'est connu ?
Réponds uniquement par un objet JSON :
{"marketplace": "existante" | "aucune" | "inconnu", "detail": "une à deux phrases en français", "technologie": "nom ou chaîne vide", "anciennete": "date ou durée connue, sinon chaîne vide", "sources": [{"url": "...", "fait": "ce que la page établit"}]}
"existante" ou "aucune" exige au moins une source. Si rien de concluant : "inconnu". N'invente rien."""


def web_check(account: dict, llm: LLMClient) -> dict:
    prompt = (f"Entreprise : {account['nom']}\nSite : {account.get('site') or 'inconnu'}\n"
              f"Pays : {account.get('pays') or 'inconnu'}\nSecteur : {account.get('secteur') or 'inconnu'}")
    try:
        result = llm.research(WEB_SYSTEM, prompt, task="web_check")
        data = extract_json(result.text)
    except LLMError as exc:
        log.warning("Vérification web impossible pour %s : %s", account["nom"], exc)
        return {"marketplace": "inconnu", "detail": "", "technologie": "", "anciennete": "",
                "sources": [], "sources_outil": [], "statut": f"échec : {exc}"}

    state = data.get("marketplace") if data.get("marketplace") in MARKETPLACE_STATES else "inconnu"
    cited = [s for s in data.get("sources", []) if isinstance(s, dict) and s.get("url")]
    if state != "inconnu" and not cited and not result.sources:
        state = "inconnu"   # affirmation sans source : refusée
    return {"marketplace": state, "detail": data.get("detail", ""), "technologie": data.get("technologie", ""),
            "anciennete": data.get("anciennete", ""), "sources": cited, "sources_outil": result.sources[:8],
            "statut": "vérifié"}


# --- Fiche d'appel (comptes à appeler) ---------------------------------------------
PITCH_SYSTEM = """Tu prépares un SDR de Mirakl à appeler un compte lundi matin. Il doit savoir quoi dire sans rappeler l'analyste.
Produits Mirakl : {products}.
À partir des seuls faits fournis (chacun a un identifiant entre crochets), écris en français, sobrement :
- "pourquoi_maintenant" : une à deux phrases, le signal le plus récent d'abord, avec sa date ;
- "ce_qui_a_change" : l'écart entre le profil Tamtam de 2024 (P…) et les événements récents (E…), en une à deux phrases ; chaîne vide si le profil disait déjà la même chose ;
- "axes" : deux ou trois axes. "besoin" = l'hypothèse de besoin formulée comme une question à poser ; "produit" = le produit Mirakl adapté ; "argument" = une ligne ; "sources" = les identifiants des faits utilisés ;
- "a_verifier" : ce que le SDR doit vérifier pendant l'appel (deux à quatre points courts).
Chaque affirmation doit venir d'un fait fourni. N'invente ni chiffre, ni nom, ni date."""

PITCH_SCHEMA = {
    "type": "object",
    "properties": {
        "pourquoi_maintenant": {"type": "string"},
        "ce_qui_a_change": {"type": "string"},
        "axes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "besoin": {"type": "string"},
                    "produit": {"type": "string", "enum": list(config.MIRAKL_PRODUCTS)},
                    "argument": {"type": "string"},
                    "sources": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["besoin", "produit", "argument", "sources"],
                "additionalProperties": False,
            },
        },
        "a_verifier": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["pourquoi_maintenant", "ce_qui_a_change", "axes", "a_verifier"],
    "additionalProperties": False,
}


def build_facts(account: dict) -> dict[str, str]:
    facts: dict[str, str] = {}
    for s in account["signaux"]:
        if s["role"] == config.ROLE_NOISE:
            continue
        origin = f" ({s['origine']})" if s["origine"] else ""
        facts[s["event_id"]] = (f"{s['date']} · {s['type']} · {s['detail']}{origin} "
                                f"[rôle : {s['role']}, {s['age_jours']} j avant l'extraction]")
    for i, m in enumerate(account["strategies"], start=1):
        text = " ".join(x for x in (m["Strategy"], m["Ecommerce"]) if x)
        if text:
            facts[f"P{i}"] = f"Profil Tamtam (photo de 2024) de {m['Name']} : {text[:900]}"
    web = account.get("verification_web") or {}
    if web.get("statut") == "vérifié":
        facts["W1"] = (f"Vérification web : marketplace {web['marketplace']}. {web['detail']} "
                       f"Technologie : {web['technologie'] or 'non identifiée'}.")
    for i, note in enumerate(account.get("a_verifier", []), start=1):
        facts[f"F{i}"] = f"Point de fit à confirmer : {note}"
    return facts


def write_pitch(account: dict, llm: LLMClient) -> dict | None:
    facts = build_facts(account)
    prompt = (f"Compte : {account['nom']} ({account.get('pays') or 'pays inconnu'}, "
              f"{account.get('secteur') or 'secteur inconnu'})\nStatut : {account['statut']}"
              f"{' (' + account['motif'] + ')' if account['motif'] else ''}\n"
              f"Palier {account['palier']} : {account['regle_palier']}\n\nFaits :\n"
              + "\n".join(f"[{k}] {v}" for k, v in facts.items()))
    system = PITCH_SYSTEM.format(products=json.dumps(config.MIRAKL_PRODUCTS, ensure_ascii=False))
    try:
        return _validated(llm.json(system, prompt, PITCH_SCHEMA, task="write_pitch", effort="medium"), facts)
    except LLMError as exc:
        log.warning("Fiche impossible pour %s : %s", account["nom"], exc)
        return None


def _validated(pitch: dict, facts: dict[str, str]) -> dict:
    """Retire les sources inconnues et les axes qui n'en ont plus."""
    axes = []
    for axe in pitch.get("axes", []):
        sources = [s.strip("[]") for s in axe.get("sources", []) if s.strip("[]") in facts]
        if sources:
            axes.append(axe | {"sources": sources})
    checks = list(pitch.get("a_verifier", []))
    dropped = len(pitch.get("axes", [])) - len(axes)
    if dropped:
        checks.append(f"{dropped} axe(s) écarté(s) faute de source vérifiable")
    return pitch | {"axes": axes, "a_verifier": checks}


# --- Raison en une phrase (tous les comptes) --------------------------------------
REASON_SYSTEM = """Tu résumes, pour l'équipe sales de Mirakl, la décision prise sur chaque compte.
Pour chaque compte, écris "raison" : une phrase en français, 25 mots au plus, qui dit pourquoi il a ce statut et cette priorité. Commence par le fait décisif (le signal, ou ce qui le met hors cible). Pas de formule creuse, pas de fait absent des données."""

REASON_SCHEMA = {
    "type": "object",
    "properties": {
        "accounts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "raison": {"type": "string"}},
                "required": ["id", "raison"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["accounts"],
    "additionalProperties": False,
}


def write_reasons(accounts: list[dict], llm: LLMClient) -> dict[int, str]:
    items = [{
        "id": str(a["groupe_id"]), "compte": a["nom"], "statut": a["statut"], "motif": a["motif"],
        "liste": a["liste"], "palier": a["palier"], "regle_palier": a["regle_palier"],
        "signaux": [f"{s['date']} {s['role']} : {s['libelle']}" for s in a["signaux"]
                    if s["role"] != config.ROLE_NOISE][:4],
    } for a in accounts]
    reasons: dict[int, str] = {}
    for start in range(0, len(items), BATCH_SIZE):
        batch = items[start:start + BATCH_SIZE]
        log.info("Raisons %d-%d / %d", start + 1, start + len(batch), len(items))
        try:
            result = llm.json(REASON_SYSTEM, json.dumps(batch, ensure_ascii=False, indent=1), REASON_SCHEMA,
                              task="write_reasons", effort="low")
        except LLMError as exc:
            log.warning("Raisons non rédigées pour ce lot : %s", exc)
            continue
        for r in result.get("accounts", []):
            if r.get("id", "").isdigit():
                reasons[int(r["id"])] = r["raison"]
    return reasons
