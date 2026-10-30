"""Hygiène des données (D11) : doublons, filiales rattachées au groupe, pays.

Le groupe est l'unité d'appel. Les regroupements sont proposés au SDR, qui les
valide avant l'analyse ; chaque fusion retenue est expliquée.
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

from . import config

# Mots retirés avant de comparer deux noms d'entreprise.
_LEGAL_WORDS = {
    "gmbh", "ag", "se", "sas", "sa", "sarl", "inc", "llc", "ltd", "co", "kg",
    "eg", "e", "g", "corp", "corporation", "company", "group", "gruppe",
    "unternehmensgruppe", "holding", "international", "incorporated", "the",
}
_GEO_WORDS = {
    "deutschland", "austria", "osterreich", "schweiz", "suisse", "espana",
    "france", "uk", "usa", "belgium", "spain", "germany", "switzerland",
}
# Hébergeurs partagés : un même domaine ne prouve pas un même groupe.
_SHARED_HOSTS = {
    "bit.ly", "recruitee.com", "linkedin.com", "facebook.com", "wixsite.com",
    "myshopify.com", "google.com", "sites.google.com",
}
_SECOND_LEVEL = {"co", "com", "org", "net", "gov", "ac"}
_STEM_STOPWORDS = {"the", "my", "shop", "group", "www"}


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def name_tokens(name: str, keep_geo: bool = False) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", _ascii(name))
    return [t for t in tokens if t not in _LEGAL_WORDS and (keep_geo or t not in _GEO_WORDS)]


# GmbH s'écrit de plusieurs façons ; AG, KG, SAS seulement en capitales
# ("Ag Processing Inc" = agriculture, pas une AG allemande).
_LEGAL_FORM_PATTERNS = {
    "gmbh": re.compile(r"\bgmbh\b", re.IGNORECASE),
    "ag": re.compile(r"\bAG\b"),
    "kg": re.compile(r"\bKG\b"),
    "sas": re.compile(r"\bSAS\b"),
    "sarl": re.compile(r"\bSARL\b"),
}


def registered_domain(url: object) -> str | None:
    """'https://www.verdalis-retail.es/x' -> 'verdalis-retail.es'."""
    if not isinstance(url, str) or "." not in url:
        return None
    host = re.sub(r"^[a-z]+://", "", url.strip().lower()).split("/")[0]
    host = host.removeprefix("www.")
    parts = host.split(".")
    if len(parts) < 2:
        return None
    take = 3 if len(parts) >= 3 and parts[-2] in _SECOND_LEVEL and len(parts[-1]) == 2 else 2
    return ".".join(parts[-take:])


def domain_stem(domain: object) -> str | None:
    """'verdalis-retail.es' -> 'verdalis' (premier segment du nom de domaine)."""
    if not isinstance(domain, str) or domain in _SHARED_HOSTS:
        return None
    stem = domain.split(".")[0].split("-")[0]
    if len(stem) < 4 or stem in _STEM_STOPWORDS:
        return None
    return stem


def country_check(name: str, website: object, declared: object) -> dict:
    """Compare le pays déclaré au domaine national et à la forme juridique."""
    domain = registered_domain(website)
    tld = domain.split(".")[-1] if domain else None
    tld_country = config.CCTLD_COUNTRY.get(tld) if tld else None
    legal = {form for form, pattern in _LEGAL_FORM_PATTERNS.items() if pattern.search(name)}
    legal_countries = set().union(*(config.LEGAL_FORM_COUNTRIES[t] for t in legal)) if legal else set()

    declared = declared if isinstance(declared, str) and declared.strip() else None
    if declared is None:
        inferred = tld_country or (next(iter(legal_countries)) if len(legal_countries) == 1 else None)
        note = f"pays manquant ; déduit : {inferred}" if inferred else "pays manquant"
        return {"country": inferred, "country_flag": "manquant", "country_note": note}

    clues = []
    if tld_country and tld_country != declared:
        clues.append(f"domaine .{tld} ({tld_country})")
    if legal_countries and declared not in legal_countries:
        clues.append(f"forme juridique {'/'.join(sorted(legal)).upper()}")
    if clues:
        inferred = tld_country or declared
        note = f"pays déclaré « {declared} » incohérent avec {' et '.join(clues)} ; probable : {inferred}"
        return {"country": inferred, "country_flag": "suspect", "country_note": note}
    return {"country": declared, "country_flag": "ok", "country_note": ""}


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        self.parent[self.find(a)] = self.find(b)


def _size_rank(band: object) -> int:
    lo_hi = config.SIZE_BANDS.get(band) if isinstance(band, str) else None
    if lo_hi is None:
        return -1
    return lo_hi[1] if lo_hi[1] is not None else 10**9


def _links(prospects: pd.DataFrame) -> tuple[pd.DataFrame, dict[frozenset[int], str]]:
    """Liens deux à deux entre fiches qui semblent être la même entreprise ou le même groupe.

    - doublon : même nom (formes juridiques retirées), ou même site ;
    - filiale : même nom hors mention géographique (INTERSPORT Austria / Deutschland),
      ou même racine de domaine égale au premier mot du nom (Verdalis).
    """
    df = prospects.copy()
    df["_tokens"] = df["Name"].map(name_tokens)
    df["_name_key"] = df["_tokens"].map(" ".join)
    df["_strict_key"] = df["Name"].map(lambda n: " ".join(name_tokens(n, keep_geo=True)))
    df["_domain"] = df["Website"].map(registered_domain)
    df["_stem"] = df["_domain"].map(domain_stem)
    links: dict[frozenset[int], str] = {}

    def link(ids: list[int], kind: str, reason: str) -> None:
        for other in ids[1:]:
            links.setdefault(frozenset((ids[0], other)), f"{kind} : {reason}")

    for key, grp in df[df["_strict_key"] != ""].groupby("_strict_key"):
        if len(grp) > 1:
            link(grp["Id"].tolist(), "doublon", f"même nom « {key} »")
    shared = df["_domain"].notna() & ~df["_domain"].isin(_SHARED_HOSTS)
    for dom, grp in df[shared].groupby("_domain"):
        if len(grp) > 1:
            link(grp["Id"].tolist(), "doublon", f"même site {dom}")
    for key, grp in df[df["_name_key"] != ""].groupby("_name_key"):
        if len(grp) > 1 and grp["_strict_key"].nunique() > 1:
            link(grp["Id"].tolist(), "filiale", f"même nom hors mention géographique « {key} »")
    first_token = df["_tokens"].map(lambda t: t[0] if t else None)
    same_stem = df["_stem"].notna() & (df["_stem"] == first_token)
    for stem, grp in df[same_stem].groupby("_stem"):
        if len(grp) > 1:
            link(grp["Id"].tolist(), "filiale", f"même marque « {stem} » (nom et domaine)")
    return df, links


def _components(ids, links: dict[frozenset[int], str]) -> dict[int, int]:
    uf = _UnionFind()
    for pair in links:
        a, b = tuple(pair)
        uf.union(a, b)
    return {i: uf.find(i) for i in ids}


def suggest_groups(prospects: pd.DataFrame) -> list[dict]:
    """Regroupements proposés au SDR, à valider avant l'analyse (fusionner ou laisser séparé)."""
    df, links = _links(prospects)
    comp = _components(df["Id"], links)
    df["_comp"] = df["Id"].map(comp)
    df["_size_rank"] = df["CompanySize"].map(_size_rank)
    suggestions = []
    for _, members in df.groupby("_comp"):
        if len(members) < 2:
            continue
        members = members.sort_values("_size_rank", ascending=False)
        ids = sorted(int(i) for i in members["Id"])
        reasons = sorted({r for k, r in links.items() if k <= set(ids)})
        suggestions.append({
            "id": "-".join(map(str, ids)),
            "type": "doublon" if all(r.startswith("doublon") for r in reasons) else "groupe",
            "motifs": reasons,
            "entites": [{
                "id": int(m["Id"]), "nom": m["Name"], "pays": _text(m["Country"]),
                "site": _text(m["Website"]), "secteur": _text(m["Industry"]),
                "taille": _text(m["CompanySize"]),
                "linkedin": None if pd.isna(m["EmployeesOnLinkedin"]) else int(m["EmployeesOnLinkedin"]),
            } for _, m in members.iterrows()],
        })
    return sorted(suggestions, key=lambda x: x["entites"][0]["nom"].lower())


def build_groups(prospects: pd.DataFrame, decisions: dict[str, bool] | None = None) -> pd.DataFrame:
    """Une ligne par groupe. `decisions` : {id de suggestion : fusionner ?} validé par le SDR ;
    une suggestion absente est fusionnée (comportement par défaut en ligne de commande)."""
    decisions = decisions or {}
    df, links = _links(prospects)
    proposed = _components(df["Id"], links)
    kept: dict[frozenset[int], str] = {}
    for comp_root in set(proposed.values()):
        ids = sorted(i for i, r in proposed.items() if r == comp_root)
        if len(ids) > 1 and decisions.get("-".join(map(str, ids)), True):
            kept.update({k: v for k, v in links.items() if k <= set(ids)})
    group_of = _components(df["Id"], kept)
    df["_group"] = df["Id"].map(group_of)
    refused = {sid for sid, merge in decisions.items() if not merge}

    df["_completeness"] = df[list(df.columns[: len(prospects.columns)])].notna().sum(axis=1)
    df["_size_rank"] = df["CompanySize"].map(_size_rank)

    rows = []
    for _, members in df.groupby("_group", sort=False):
        members = members.sort_values(["_size_rank", "_completeness"], ascending=False)
        head = members.iloc[0]
        record = head[list(prospects.columns)].to_dict()
        ids = members["Id"].tolist()
        record["GroupId"] = int(head["Id"])
        record["MemberIds"] = ids
        record["MemberNames"] = members["Name"].tolist()
        reasons = sorted({kept[k] for k in kept if k <= set(ids)})
        if len(ids) > 1:
            others = ", ".join(f"{n} ({i})" for n, i in zip(members["Name"][1:], ids[1:]))
            record["MergeNote"] = (
                f"Groupe retenu : {head['Name']} ({head['Id']}), plus grande taille déclarée puis "
                f"fiche la plus complète. Rattachés : {others}. Motifs : {' ; '.join(reasons)}. Validé avant analyse."
            )
        else:
            split = next((sid for sid in refused if str(int(head["Id"])) in sid.split("-")), None)
            record["MergeNote"] = f"Laissé séparé à la validation (suggestion {split})." if split else ""
        # Textes de stratégie de toutes les entités : utile pour repérer
        # les contradictions (Klarion) et l'écart profil / événements (D3).
        record["MemberStrategies"] = [
            {"Id": int(m["Id"]), "Name": m["Name"], "Strategy": _text(m["Strategy"]),
             "Ecommerce": _text(m["E-commerce in Strat"])}
            for _, m in members.iterrows()
        ]
        record.update(country_check(head["Name"], head["Website"], head["Country"]))
        record["DeclaredCountry"] = head["Country"]
        rows.append(record)

    groups = pd.DataFrame(rows)
    return groups.sort_values("GroupId").reset_index(drop=True)


def attach_events(events: pd.DataFrame, groups: pd.DataFrame) -> pd.DataFrame:
    """Rattache chaque événement à son groupe et note sa filiale d'origine."""
    member_to_group = {m: g for g, ms in zip(groups["GroupId"], groups["MemberIds"]) for m in ms}
    group_names = dict(zip(groups["GroupId"], groups["Name"]))
    ev = events.copy()
    ev["GroupId"] = ev["AccountId"].map(member_to_group).astype("int64")
    ev["Origin"] = [
        "" if acc == gid else f"signal venu de {name}"
        for acc, gid, name in zip(ev["AccountId"], ev["GroupId"], ev["AccountName"])
    ]
    ev["GroupName"] = ev["GroupId"].map(group_names)
    return ev


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""
