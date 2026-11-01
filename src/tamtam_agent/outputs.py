"""Écriture des livrables dans outputs/<date d'extraction>/ (et la mémoire dans outputs/)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd

from . import config
from .agent import RunResult
from .enrich import fr_date


def write_all(result: RunResult, out_dir: Path) -> dict[str, Path]:
    run_dir = out_dir / "runs" / result.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "meta": run_dir / "meta.json",
        "tam_csv": run_dir / "tam_priorise.csv",
        "tam_xlsx": run_dir / "tam_priorise.xlsx",
        "top20": run_dir / "top20.md",
        "explications": run_dir / "explications.jsonl",
        "limites": run_dir / "limites_des_donnees.md",
        "memoire": out_dir / "memoire.csv",
    }
    tam = tam_table(result.accounts)
    paths["tam_csv"].write_bytes(csv_bytes(tam))
    paths["tam_xlsx"].write_bytes(xlsx_bytes(export_sheets(tam, "complet", result.limits)))
    paths["top20"].write_text(top20_markdown(result))
    with paths["explications"].open("w") as f:
        for a in result.accounts:
            f.write(json.dumps(explanation(a), ensure_ascii=False, default=str) + "\n")
    paths["limites"].write_text(limits_markdown(result))
    paths["meta"].write_text(json.dumps({
        "run_id": result.run_id, "source": result.source,
        "extraction": result.extraction_date.date().isoformat(), "traitement": result.run_date.isoformat(),
        "llm": result.llm_label, "explique": result.explained, "fraicheur_jours": result.limits["fraicheur"]["jours"],
        "top": len(result.top), "groupes": len(result.accounts),
        "top_ids": [a["groupe_id"] for a in result.top],
        "statuts": {s: sum(a["statut"] == s for a in result.accounts)
                    for s in (config.STATUS_QUALIFIED, config.STATUS_DIG, config.STATUS_DISQUALIFIED)},
        "paliers_top": {t: sum(a["palier"] == t for a in result.top) for t in "ABC"},
        "limites": result.limits,
        "sortis": result.gone[["groupe_id", "compte", "palier"]].to_dict("records") if not result.gone.empty else [],
    }, ensure_ascii=False, indent=1, default=str))
    result.memory.to_csv(paths["memoire"], index=False)
    return paths


# --- TAM ---------------------------------------------------------------------
INT_COLUMNS = ["rang", "rang top 20", "profils LinkedIn", "groupe id"]


def tam_table(accounts: list[dict]) -> pd.DataFrame:
    return _int_columns(pd.DataFrame([{
        "rang": i,
        "compte": a["nom"],
        "statut": a["statut"],
        "priorité (palier)": a["palier"],
        "raison": a["raison"],
        "règle du palier": a["regle_palier"],
        "motif": a["motif"],
        "liste": a["liste"],
        "rang top 20": a["rang_top"],
        "à qualifier avant d'appeler": "oui" if a["a_qualifier"] else "",
        "dernier déclencheur": a["dernier_declencheur"],
        "pays": a["pays"],
        "secteur": a["secteur"],
        "taille déclarée": a["taille"],
        "profils LinkedIn": a["profils_linkedin"],
        "confiance": a["confiance"],
        "évolution": a["evolution"],
        "évolution (détail)": a["evolution_detail"],
        "site": a["site"],
        "entités rattachées": " | ".join(a["entites"]) if len(a["entites"]) > 1 else "",
        "groupe id": a["groupe_id"],
    } for i, a in enumerate(accounts, start=1)]))


def read_tam(xlsx: Path) -> pd.DataFrame:
    """Relit le TAM d'une analyse depuis son Excel (source des exports)."""
    return _int_columns(pd.read_excel(xlsx, sheet_name=EXPORT_LISTS["tous"]))


def _int_columns(df: pd.DataFrame) -> pd.DataFrame:
    # Entiers avec cases vides : sinon pandas écrit « 3.0 ».
    for col in INT_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    return df


# Listes exportables : clé -> (nom de l'onglet, filtre sur le TAM). « complet » les réunit toutes.
EXPORT_LISTS = {
    "top": "Top 20",
    "tous": "TAM priorisé",
    "surveiller": "Hors cible à surveiller",
    "clients": "Clients Mirakl",
}


def export_sheets(tam: pd.DataFrame, liste: str, limits: dict | None = None) -> dict[str, pd.DataFrame]:
    """Onglets d'un export : une liste, ou toutes (« complet », avec les limites des données)."""
    tables = {
        "top": tam[tam["rang top 20"].notna()].sort_values("rang top 20"),
        "tous": tam,
        "surveiller": tam[tam["liste"] == config.LIST_WATCH],
        "clients": tam[tam["liste"] == config.LIST_CLIENTS],
    }
    if liste != "complet":
        return {EXPORT_LISTS[liste]: tables[liste]}
    sheets = {EXPORT_LISTS[k]: df for k, df in tables.items()}
    if limits:
        sheets["Limites"] = pd.DataFrame({"limite": _limit_lines(limits)})
    return sheets


def xlsx_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)
            ws = writer.sheets[name]
            ws.freeze_panes = "B2"
            ws.auto_filter.ref = ws.dimensions
            for col_cells in ws.columns:
                width = max(len(str(c.value or "")) for c in col_cells[:60])
                ws.column_dimensions[col_cells[0].column_letter].width = min(max(10, width + 2), 70)
    return buffer.getvalue()


def csv_bytes(df: pd.DataFrame) -> bytes:
    """CSV lisible par Excel en français : séparateur « ; » et BOM UTF-8 (sinon tout tient dans la colonne A)."""
    return df.to_csv(index=False, sep=";").encode("utf-8-sig")


# --- Top 20 pour les SDR -------------------------------------------------------
def top20_markdown(result: RunResult) -> str:
    fresh = result.limits["fraicheur"]
    top = result.top
    n_a, n_b, n_c = (sum(a["palier"] == t for a in top) for t in "ABC")
    lines = [
        f"# Top {len(top)} Mirakl : qui appeler en premier",
        "",
        f"Traitement du {fr_date(result.run_date)} · données arrêtées au {fr_date(fresh['extraction'])} · "
        f"LLM : {result.llm_label}",
        "",
        f"> **Fraîcheur** : le signal le plus récent date du {fr_date(fresh['extraction'])}, "
        f"soit {fresh['jours']} jours avant ce traitement. Les âges indiqués sont comptés depuis cette date. "
        "Vérifiez en début d'appel que le sujet est toujours ouvert.",
        "",
    ]
    if not result.explained:
        lines += ["> **Textes non rédigés** : analyse lancée sans clé LLM. Statuts et paliers sont calculés ; "
                  "les fiches, raisons et vérifications web demandent une clé (Paramètres).", ""]
    lines += [
        f"{n_a} comptes en palier A, {n_b} en palier B"
        + (f", complétés par {n_c} comptes en palier C à qualifier avant d'appeler." if n_c else "."),
        "",
        "| # | Compte | Pays | Palier | Statut | Signal principal |",
        "|---|---|---|---|---|---|",
    ]
    for a in top:
        trig = next((s for s in a["signaux"] if s["role"] == config.ROLE_TRIGGER), None)
        best = trig or next((s for s in a["signaux"] if s["role"] == config.ROLE_AMPLIFIER), None)
        sig = f"{best['libelle']} ({fr_date(best['date'])})" if best else ""
        tier = f"{a['palier']} (à qualifier)" if a["a_qualifier"] else a["palier"]
        lines.append(f"| {a['rang_top']} | {a['nom']} | {a['pays'] or '?'} | {tier} | {a['statut']} | {sig} |")
    lines.append("")

    for a in top:
        lines += _account_card(a)

    rest = [a for a in result.accounts if a["statut"] != config.STATUS_DISQUALIFIED
            and a["palier"] == "C" and not a["rang_top"]][:15]
    if rest:
        lines += ["## Ensuite : à creuser (palier C)", "",
                  "Pas de déclencheur récent : à qualifier avant d'appeler.", ""]
        lines += [f"- **{a['nom']}** ({a['pays'] or '?'}) : {a['raison'] or a['regle_palier']}" for a in rest]
        lines.append("")
    watch = [a for a in result.accounts if a["liste"] == config.LIST_WATCH]
    if watch:
        lines += ["## Hors ICP à surveiller", "",
                  "Signaux réels mais hors cible (secteur, taille ou zone) : pas dans le Top par défaut.", ""]
        lines += [f"- **{a['nom']}**, palier {a['palier']} : {a['raison'] or a['motif']}" for a in watch]
        lines.append("")
    clients = [a for a in result.accounts if a["liste"] == config.LIST_CLIENTS]
    if clients:
        lines += ["## Clients Mirakl à développer", "",
                  "Mirakl détecté : à transmettre aux account managers (Ads, Connect), pas à prospecter.", ""]
        lines += [f"- **{a['nom']}** : {a['motif']}" for a in clients]
        lines.append("")
    return "\n".join(lines)


def _account_card(a: dict) -> list[str]:
    pitch = a.get("pitch") or {}
    size = a["taille"] or "?"
    li = f", {a['profils_linkedin']} profils LinkedIn" if a["profils_linkedin"] else ""
    lines = [
        f"## {a['rang_top']}. {a['nom']}",
        "",
        f"Palier **{a['palier']}** ({a['regle_palier']}) · {a['statut']} · {a['pays'] or 'pays inconnu'} · "
        f"{a['secteur'] or 'secteur inconnu'} · {size}{li}" + (f" · {a['site']}" if a["site"] else ""),
        "",
    ]
    trig = next((s for s in a["signaux"] if s["role"] == config.ROLE_TRIGGER), None)
    if pitch.get("pourquoi_maintenant"):
        lines += [f"**Pourquoi maintenant** : {pitch['pourquoi_maintenant']}", ""]
    elif trig:
        lines += [f"**Signal** [{trig['event_id']}] : {trig['libelle']} ({fr_date(trig['date'])})", ""]
    if pitch.get("ce_qui_a_change"):
        lines += [f"**Ce qui a changé depuis le profil Tamtam (2024)** : {pitch['ce_qui_a_change']}", ""]
    web = a.get("verification_web")
    if web:
        state = {"existante": "marketplace déjà en place", "aucune": "pas de marketplace trouvée",
                 "inconnu": "non déterminé"}[web["marketplace"]]
        detail = f" : {web['detail']}" if web.get("detail") else ""
        if web["statut"] == "vérifié":
            lines += [f"**Marketplace aujourd'hui** [W1] : {state}{detail}", ""]
        else:
            lines += [f"**Marketplace aujourd'hui** : non vérifiée ({web['statut']}).", ""]
    if pitch.get("axes"):
        lines.append("**Axes d'approche**")
        lines.append("")
        for i, axe in enumerate(pitch["axes"], start=1):
            refs = " ".join(f"[{s}]" for s in axe["sources"])
            lines.append(f"{i}. *{axe['besoin']}* → **{axe['produit']}** : {axe['argument']} {refs}")
        lines.append("")
    doubts = explanation(a)["incertitudes"]
    if a["fusion"]:
        doubts.append(a["fusion"])
    if doubts:
        lines += ["**À vérifier**", ""] + [f"- {d}" for d in doubts] + [""]
    lines += ["<details><summary>Sources</summary>", ""]
    for s in a["signaux"]:
        if s["role"] != config.ROLE_NOISE:
            origin = f", {s['origine']}" if s["origine"] else ""
            lines.append(f"- [{s['event_id']}] {fr_date(s['date'])} · {s['type']} · {s['libelle']}{origin} "
                         f"→ {s['role']} ({s['raison']})")
    for i, m in enumerate(a["strategies"], start=1):
        if m["Strategy"] or m["Ecommerce"]:
            lines.append(f"- [P{i}] profil Tamtam 2024 de {m['Name']} (tamtam_prospects, Id {m['Id']})")
    if web:
        for src in web.get("sources", []) + web.get("sources_outil", []):
            label = src.get("fait") or src.get("titre") or ""
            lines.append(f"- [W1] {src['url']}" + (f" : {label}" if label else ""))
    lines += ["", "</details>", ""]
    return lines


# --- Explications structurées -----------------------------------------------
def explanation(a: dict) -> dict:
    events = [s for s in a["signaux"] if s["role"] != config.ROLE_NOISE]
    decisions = [
        {"decision": "statut", "valeur": a["statut"], "motif": a["motif"], "liste": a["liste"],
         "regle_appliquee": {k: v["regle"] for k, v in a["fit"].items()},
         "donnee_source": f"tamtam_prospects Id {a['groupe_id']} : secteur={a['secteur'] or '?'}, "
                          f"pays={a['pays'] or '?'}, taille={a['taille'] or '?'}, LinkedIn={a['profils_linkedin']}",
         "confiance": a["confiance"]},
        {"decision": "palier", "valeur": a["palier"], "regle_appliquee": a["regle_palier"],
         "donnee_source": [f"events {s['event_id']}" for s in events],
         "role_des_signaux": {s["event_id"]: s["role"] for s in events}},
    ]
    if a["fusion"]:
        decisions.append({"decision": "fusion", "valeur": a["entites"], "regle_appliquee": a["fusion"]})
    if a["pays_note"]:
        decisions.append({"decision": "pays", "valeur": a["pays"], "regle_appliquee": a["pays_note"]})

    pitch = a.get("pitch") or {}
    web = a.get("verification_web") or {}
    uncertain = [f"Fit à confirmer : {f['detail']}" for f in a["fit"].values() if f["niveau"] == "incertain"]
    uncertain += a["a_verifier"] + pitch.get("a_verifier", [])
    uncertain = list(dict.fromkeys(uncertain))
    sources = [f"events:{s['event_id']}" for s in events] + [f"tamtam_prospects:{a['groupe_id']}"]
    sources += [s["url"] for s in web.get("sources", [])]
    return {
        "groupe_id": a["groupe_id"], "compte": a["nom"], "statut": a["statut"], "palier": a["palier"],
        "regle_palier": a["regle_palier"], "rang_top": a["rang_top"], "motif": a["motif"], "liste": a["liste"],
        "pays": a["pays"], "secteur": a["secteur"], "taille": a["taille"],
        "profils_linkedin": a["profils_linkedin"], "site": a["site"], "entites": a["entites"],
        "fusion": a["fusion"], "raison": a["raison"], "confiance": a["confiance"], "evolution": a["evolution"],
        "decisions": decisions, "fit": a["fit"], "signaux": events,
        "verification_web": web or None, "argumentaire": pitch or None,
        "a_verifier": a["a_verifier"], "incertitudes": uncertain, "sources": sources,
        "a_qualifier": a["a_qualifier"], "dernier_signal": a["dernier_signal"],
    }


# --- Limites ------------------------------------------------------------------
def _limit_lines(lim: dict) -> list[str]:
    lines = [f"Fraîcheur : extraction du {lim['fraicheur']['extraction']}, "
             f"{lim['fraicheur']['jours']} jours avant le traitement.", lim["evenements"], lim["groupes"]]
    lines += [f"CRM : {x}" for x in lim["crm"]]
    lines += [f"Fusion : {x}" for x in lim["fusions"]]
    lines += [f"Pays : {x}" for x in lim["pays"]]
    lines += [f"Taille : {x}" for x in lim["tailles"]]
    return lines


def limits_markdown(result: RunResult) -> str:
    lim = result.limits
    out = [
        "# Limites des données",
        "",
        "Signalées, pas corrigées en silence. À dire en restitution.",
        "",
        "## Fraîcheur et nature des données",
        "",
        f"- Dernier événement : {fr_date(lim['fraicheur']['extraction'])} ; traitement : "
        f"{fr_date(lim['fraicheur']['traitement'])} ({lim['fraicheur']['jours']} jours). "
        "La récence est mesurée par rapport à l'extraction (D12).",
        f"- {lim['evenements']}",
        f"- {lim['groupes']}",
        "",
        "## CRM Mirakl",
        "",
        *[f"- {x}" for x in lim["crm"]],
        "",
    ]
    sections = [("Fusions de comptes (D11)", lim["fusions"]), ("Pays manquants ou suspects", lim["pays"]),
                ("Tailles à confirmer", lim["tailles"])]
    for title, items in sections:
        if items:
            out += [f"## {title}", "", *[f"- {x}" for x in items], ""]
    if not result.gone.empty:
        out += ["## Comptes sortis de l'export depuis la dernière exécution", "",
                *[f"- {r.compte} (palier {r.palier})" for r in result.gone.itertuples()], ""]
    return "\n".join(out)
