"""Pipeline de l'agent : Excel validé -> Top 20, TAM priorisé, explications, mémoire.

Les règles décident (statut, palier, ordre) ; le LLM, s'il est configuré, rédige
les textes et vérifie le web. Même export, mêmes décisions : même Top 20.
Couche sémantique : un petit modèle local relit les rôles donnés par les règles
et corrige les cas nets, marqués « à relire » (voir semantic.py).
Option « évolutions » : le LLM juge l'évolution de chaque compte depuis l'analyse
précédente ; une évolution nette devient un déclencheur (voir evolution.py).

Chaque étape est annoncée par un log portant `extra={"etape": ...}`, que l'interface
affiche comme une progression (voir STEPS).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from . import config, enrich, evolution as evolutions, icp, memory, semantic, signals
from .clean import attach_events, build_groups, registered_domain
from .llm import LLMError, get_llm
from .load import load_case_data
from .tiers import TIER_ORDER, assign_tier

log = logging.getLogger(__name__)
STATUS_ORDER = {config.STATUS_QUALIFIED: 0, config.STATUS_DIG: 1, config.STATUS_DISQUALIFIED: 2}

# Étapes affichées pendant l'analyse : clé -> libellé.
STEPS = {
    "donnees": "Lecture de l'export et des regroupements",
    "modele": "Chargement du modèle d'analyse sémantique",
    "signaux": "Rôle de chaque événement",
    "evolutions": "Évolutions depuis l'analyse précédente",
    "paliers": "Statuts, paliers et Top 20",
    "web": "Vérification web des comptes du Top",
    "fiches": "Fiches d'appel",
    "raisons": "Raisons de chaque compte",
    "ecriture": "Écriture des résultats",
}


def planned_steps(llm: bool, web: bool, evolution: bool, semantic_layer: bool = True) -> list[str]:
    skip = {"modele": not semantic_layer, "evolutions": not (evolution and llm), "web": not (llm and web),
            "fiches": not llm, "raisons": not llm}
    return [k for k in STEPS if not skip.get(k)]


def _step(key: str) -> None:
    log.info(STEPS[key], extra={"etape": key})


@dataclass
class RunResult:
    run_id: str
    accounts: list[dict]
    top: list[dict]
    extraction_date: pd.Timestamp
    run_date: date
    llm_label: str
    limits: dict
    gone: pd.DataFrame
    memory: pd.DataFrame = field(repr=False, default_factory=pd.DataFrame)
    explained: bool = False   # textes rédigés par un LLM ?
    source: str = ""
    evolution: dict | None = None   # option évolutions : base de comparaison et décompte


def new_run_id() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def run(data_path: Path, out_dir: Path, provider: str = "auto", web: bool = True,
        top_n: int = config.TOP_N, cache_dir: Path | None = None, run_date: date | None = None,
        api_key: str | None = None, group_decisions: dict[str, bool] | None = None,
        run_id: str | None = None, model: str | None = None, evolution: bool = False,
        semantic_layer: bool = True) -> RunResult:
    run_date = run_date or date.today()
    run_id = run_id or new_run_id()
    _step("donnees")
    data = load_case_data(data_path)
    extraction = data.extraction_date
    run_dir = out_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    llm = get_llm(provider, cache_dir, api_key, model)
    if llm:
        llm.log_path = run_dir / "llm_log.jsonl"
    llm_label = f"{llm.provider} / {llm.model}" if llm else "aucun (règles seules)"
    log.info("Extraction du %s, LLM : %s", extraction.date(), llm_label)

    log.info("Groupes : application des regroupements validés")
    groups = build_groups(data.prospects, group_decisions)
    events = attach_events(data.events[data.events["AccountId"].isin(data.prospects["Id"])], groups)
    if semantic_layer:
        _step("modele")
        try:
            semantic.preload()
        except Exception as exc:   # modèle absent ou dépendance manquante : règles seules
            log.warning("Modèle sémantique indisponible (%s) : rôles donnés par les règles seules", exc)
            semantic_layer = False
    _step("signaux")
    log.info("Typage de %d événements par les règles", len(events))
    try:
        events = signals.classify_events(events, llm)
    except LLMError as exc:
        log.warning("Traduction des événements impossible (%s) : textes d'origine", exc)
        events = signals.classify_events(events, None)
    if semantic_layer:
        events = semantic.refine(events)

    verdicts, evolution_info = {}, None
    if evolution:
        _step("evolutions")
        verdicts, evolution_info = _evolutions(groups, events, extraction, out_dir / "runs", llm)
        if verdicts:
            events = pd.concat([events, evolutions.as_events(verdicts)], ignore_index=True)

    _step("paliers")
    events_by_group = dict(tuple(events.groupby("GroupId")))
    empty = events.iloc[0:0]
    accounts = []
    for _, row in groups.iterrows():
        fit = icp.evaluate(row)
        tier = assign_tier(events_by_group.get(row["GroupId"], empty), extraction)
        accounts.append(_account(row, fit, tier))
        accounts[-1]["evolution_mp"] = verdicts.get(int(row["GroupId"]))
    accounts.sort(key=_sort_key)

    # Top 20 : paliers A puis B, complété par les meilleurs palier C ; jamais un disqualifié.
    top = [a for a in accounts if a["statut"] != config.STATUS_DISQUALIFIED
           and a["palier"] in ("A", "B", "C")][:top_n]
    for i, a in enumerate(top, start=1):
        a["rang_top"] = i
        a["a_qualifier"] = a["palier"] == "C"
    log.info("Top %d : %d A, %d B, %d C", len(top), *(sum(a["palier"] == t for a in top) for t in "ABC"))

    if llm:
        checked = top[: config.WEB_CHECK_MAX_ACCOUNTS] if web else []
        if checked:
            _step("web")
        for i, a in enumerate(checked, start=1):
            log.info("Vérification web %d/%d : %s", i, len(checked), a["nom"])
            a["verification_web"] = enrich.web_check(a, llm)
        _step("fiches")
        for i, a in enumerate(top, start=1):
            log.info("Fiche d'appel %d/%d : %s", i, len(top), a["nom"])
            a["pitch"] = enrich.write_pitch(a, llm)
        _step("raisons")
        reasons = enrich.write_reasons(accounts, llm)
    else:
        log.info("Pas de clé LLM : décisions calculées, aucun texte rédigé")
        reasons = {}
    for a in accounts:
        a["raison"] = reasons.get(a["groupe_id"], "")
        a["confiance"] = _confidence(a)

    # Mémoire : la raison rédigée, à défaut la règle de palier.
    table = pd.DataFrame({"groupe_id": [a["groupe_id"] for a in accounts],
                          "compte": [a["nom"] for a in accounts],
                          "statut": [a["statut"] for a in accounts],
                          "palier": [a["palier"] for a in accounts],
                          "raison": [a["raison"] or a["regle_palier"] for a in accounts]})
    memory_path = out_dir / "memoire.csv"
    previous = memory.load(memory_path)
    compared = memory.compare(table, previous, extraction.date().isoformat())
    for a, evo, detail in zip(accounts, compared["evolution"], compared["evolution_detail"]):
        a["evolution"], a["evolution_detail"] = evo, detail
    new_memory, gone = memory.update(table, previous, extraction.date().isoformat(), run_date.isoformat())

    limits = data_limits(data, groups, events, accounts, extraction, run_date)
    return RunResult(run_id, accounts, top, extraction, run_date, llm_label, limits, gone, new_memory,
                     llm is not None, Path(data_path).name, evolution_info)


def _evolutions(groups, events, extraction, runs_dir: Path, llm) -> tuple[dict[int, dict], dict]:
    if llm is None:
        log.warning("Évolutions demandées sans clé LLM : non évaluées")
        return {}, {"base": None, "message": "non évaluées : pas de clé LLM"}
    base = evolutions.previous_run(runs_dir, extraction)
    if base is None:
        log.info("Évolutions : aucune analyse d'un export plus ancien, rien à comparer")
        return {}, {"base": None, "message": "aucune analyse d'un export plus ancien"}
    verdicts = evolutions.assess(groups, events, base, llm)
    counts = {v: sum(x["verdict"] == v for x in verdicts.values()) for v in evolutions.VERDICTS}
    log.info("Évolutions : %d nettes, %d faibles", counts["nette"], counts["faible"])
    return verdicts, {"base": base.run_id, "extraction_base": base.extraction, "evalues": len(verdicts), **counts}


def _account(row: pd.Series, fit: icp.IcpResult, tier) -> dict:
    status, motif, liste = fit.status, fit.motif, ""
    if tier.is_client:
        client_event = next(s for s in tier.signals if s["role"] == config.ROLE_CLIENT)
        status, liste = config.STATUS_DISQUALIFIED, config.LIST_CLIENTS
        motif = f"client Mirakl ({client_event['detail']}, {client_event['date']})"
    elif status == config.STATUS_DISQUALIFIED and tier.tier in ("A", "B", "C"):
        liste = config.LIST_WATCH
    return {
        "groupe_id": int(row["GroupId"]),
        "nom": row["Name"],
        "site": row["Website"] if isinstance(row["Website"], str) else "",
        "pays": row["country"] if isinstance(row["country"], str) else "",
        "pays_note": row["country_note"],
        "secteur": row["Industry"] if isinstance(row["Industry"], str) else "",
        "activite": row["Activity"] if isinstance(row["Activity"], str) else "",
        "taille": row["CompanySize"] if isinstance(row["CompanySize"], str) else "",
        "profils_linkedin": None if pd.isna(row["EmployeesOnLinkedin"]) else int(row["EmployeesOnLinkedin"]),
        "statut": status,
        "motif": motif,
        "liste": liste,
        "palier": tier.tier,
        "regle_palier": tier.rule,
        "dernier_declencheur": tier.last_trigger.date().isoformat() if tier.last_trigger is not None else "",
        "dernier_signal": _last_useful_signal(tier.signals),
        "fit": {name: {"niveau": f.level, "detail": f.detail, "regle": f.rule}
                for name, f in (("secteur", fit.sector), ("geographie", fit.geo), ("taille", fit.size))},
        "geo_priority": fit.geo_priority,
        "signaux": tier.signals,
        "strategies": row["MemberStrategies"],
        "entites": [f"{n} ({i})" for n, i in zip(row["MemberNames"], row["MemberIds"])],
        "fusion": row["MergeNote"],
        "a_verifier": fit.to_check + [f"Signal à relire, {s['reclasse']} : {s['libelle']}"
                                      for s in tier.signals if s["reclasse"]],
        "verification_web": None,
        "pitch": None,
        "rang_top": None,
        "a_qualifier": False,
    }


def _last_useful_signal(signals: list[dict]) -> str:
    """Date du déclencheur le plus récent ; sinon du dernier déclencheur ou amplificateur, même ancien."""
    useful = [s["date"] for s in signals if s["role"] == config.ROLE_TRIGGER and s["fenetre"] != "ancien"]
    useful = useful or [s["date"] for s in signals if s["role"] in (config.ROLE_TRIGGER, config.ROLE_AMPLIFIER)]
    return max(useful, default="")


def _sort_key(a: dict):
    """Dans un palier : signal le plus récent d'abord, puis statut, puis zone (D9)."""
    if a["liste"] == config.LIST_CLIENTS:
        group = 3
    elif a["statut"] == config.STATUS_DISQUALIFIED:
        group = 2 if a["liste"] else 4
    else:
        group = 0 if a["palier"] in ("A", "B", "C") else 1
    recency = -pd.Timestamp(a["dernier_signal"]).value if a["dernier_signal"] else 0
    return (group, TIER_ORDER[a["palier"]], recency, STATUS_ORDER[a["statut"]], a["geo_priority"], a["nom"])


def _confidence(a: dict) -> str:
    if "suspect" in a["pays_note"]:
        return "basse"
    uncertain = sum(f["niveau"] == icp.UNCERTAIN for f in a["fit"].values())
    if a["statut"] == config.STATUS_QUALIFIED:
        return "moyenne" if a["a_verifier"] else "haute"
    return "basse" if uncertain >= 2 else "moyenne"


def data_limits(data, groups: pd.DataFrame, events: pd.DataFrame, accounts: list[dict],
                extraction: pd.Timestamp, run_date: date) -> dict:
    """Anomalies à signaler (D10) : rien n'est corrigé en silence."""
    crm = data.crm
    crm_notes = []
    for (dom, country), grp in crm.groupby(["Domain", "Country"]):
        if len(grp) > 1:
            crm_notes.append(f"Doublon probable : {', '.join(grp['AccountId'])} (même domaine {dom}, même pays {country}).")
    names = dict(zip(crm["AccountId"], crm["Name"]))
    for row in crm.itertuples():
        parent = row.ParentAccountId
        if isinstance(parent, str) and "mirakl" not in names.get(parent, "").lower():
            crm_notes.append(f"Parent incohérent : {row.AccountId} ({row.Name}) rattaché à {parent} "
                             f"({names.get(parent, 'inconnu')}), hors groupe Mirakl.")
    crm_domains = set(crm["Domain"].dropna().str.lower())
    prospect_domains = {registered_domain(w) for w in data.prospects["Website"]}
    crm_names = set(crm["Name"].str.lower())
    joins = len(crm_domains & prospect_domains) + len(crm_names & set(data.prospects["Name"].str.lower()))
    crm_notes.append(
        f"L'onglet CRM contient {len(crm)} entités du groupe Mirakl, pas des clients : {joins} correspondance "
        "avec les prospects. Les clients existants ne peuvent être repérés que par les événements "
        "(Mirakl détecté).")

    orphans = len(data.orphan_events)
    return {
        "fraicheur": {"extraction": extraction.date().isoformat(), "traitement": run_date.isoformat(),
                      "jours": (pd.Timestamp(run_date) - extraction).days},
        "crm": crm_notes,
        "fusions": [a["fusion"] for a in accounts if a["fusion"]],
        "pays": [f"{a['nom']} : {a['pays_note']}" for a in accounts if a["pays_note"]],
        "tailles": [f"{a['nom']} : {', '.join(a['a_verifier'])}" for a in accounts if a["a_verifier"]],
        "evenements": f"{len(events)} événements sur {events['GroupId'].nunique()} groupes"
                      + (f" ; {orphans} événement(s) sans prospect correspondant, ignoré(s)" if orphans else "") + ".",
        "groupes": f"{len(data.prospects)} lignes prospects -> {len(groups)} groupes.",
    }
