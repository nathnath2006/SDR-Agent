"""Fit ICP (D1) : secteur, géographie, taille -> statut.

Le statut mesure le fit, pas le timing (décision du 2026-10-29) :
qualifié = dans l'ICP ; à creuser = fit incertain ; disqualifié = clairement hors.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import config

IN, UNCERTAIN, OUT = "dans", "incertain", "hors"


@dataclass
class Fit:
    level: str          # dans / incertain / hors
    detail: str         # phrase lisible par un SDR
    rule: str           # règle appliquée, pour l'audit
    to_check: str = ""  # point à vérifier, même quand le critère passe


@dataclass
class IcpResult:
    sector: Fit
    geo: Fit
    size: Fit
    geo_priority: int   # 1 = FR/DACH, 2 = reste de l'Europe, 3 = US, 9 = hors / inconnu

    @property
    def status(self) -> str:
        levels = {self.sector.level, self.geo.level, self.size.level}
        if OUT in levels:
            return config.STATUS_DISQUALIFIED
        if UNCERTAIN in levels:
            return config.STATUS_DIG
        return config.STATUS_QUALIFIED

    @property
    def motif(self) -> str:
        """Ce qui empêche le statut 'qualifié', le plus bloquant d'abord."""
        for level in (OUT, UNCERTAIN):
            parts = [f.detail for f in (self.sector, self.geo, self.size) if f.level == level]
            if parts:
                return " ; ".join(parts)
        return ""

    @property
    def to_check(self) -> list[str]:
        return [f.to_check for f in (self.sector, self.geo, self.size) if f.to_check]


def sector_fit(industry: object) -> Fit:
    """Secteur cible / adjacent / hors, d'après la table de config.py."""
    if not isinstance(industry, str) or not industry.strip():
        return Fit(UNCERTAIN, "secteur non renseigné", "secteur manquant")
    if industry in config.SECTOR_TARGET:
        return Fit(IN, f"secteur {industry}", "secteur cible (retail, distribution, biens de conso)")
    if industry in config.SECTOR_ADJACENT:
        return Fit(UNCERTAIN, f"secteur {industry} (adjacent : ambition marketplace à vérifier)", "secteur adjacent")
    return Fit(OUT, f"hors secteur ({industry})", "secteur hors ICP")


def geo_fit(country: object, country_flag: str, country_note: str) -> tuple[Fit, int]:
    if not isinstance(country, str) or not country:
        return Fit(UNCERTAIN, "pays inconnu", "pays manquant"), 9
    if country in config.GEO_PRIORITY_1:
        priority, fit = 1, Fit(IN, f"{country} (prioritaire)", "France / DACH")
    elif country in config.EUROPE:
        priority, fit = 2, Fit(IN, f"{country} (Europe)", "Europe hors FR / DACH")
    elif country in config.US:
        priority, fit = 3, Fit(IN, f"{country} (accepté)", "US accepté")
    else:
        return Fit(OUT, f"hors zone ({country})", "pays hors Europe / US"), 9
    if country_flag in ("suspect", "manquant"):
        # Pays déduit (domaine, forme juridique) : plausible mais à confirmer.
        return Fit(UNCERTAIN, country_note, "pays déduit, à confirmer"), priority
    return fit, priority


def size_fit(band: object, linkedin: object) -> Fit:
    """La bande déclarée fait foi ; LinkedIn ne sert qu'à confirmer.

    Tout le monde n'est pas sur LinkedIn (salariés de magasin) : le nombre de
    profils est un plancher. Une bande hors de 100 à 1 500 disqualifie, quoi que
    dise LinkedIn. LinkedIn ne tranche qu'une bande à cheval sur 1 500 (1001-5000) :
    plus de 1 500 profils prouve que l'entreprise dépasse le seuil.
    """
    li = int(linkedin) if isinstance(linkedin, (int, float)) and not pd.isna(linkedin) else None
    li_txt = f"{li} profils LinkedIn" if li is not None else "profils LinkedIn inconnus"
    bounds = config.SIZE_BANDS.get(band) if isinstance(band, str) else None

    if bounds is None:
        if li is not None and li > config.SIZE_MAX:
            return Fit(OUT, f"taille hors ICP ({li_txt}, bande non renseignée)", "LinkedIn > 1 500")
        if li is not None and li >= config.SIZE_MIN:
            return Fit(IN, f"taille dans l'ICP ({li_txt}, bande non renseignée)", "estimée par LinkedIn",
                       to_check="taille : bande non renseignée, estimée par LinkedIn")
        return Fit(UNCERTAIN, f"taille inconnue ({li_txt}, bande non renseignée)", "aucune estimation dans la cible")

    lo, hi = bounds
    label = f"bande {band}, {li_txt}"
    if lo > config.SIZE_MAX or (hi is not None and hi < config.SIZE_MIN):
        return Fit(OUT, f"taille hors ICP ({label})", "bande déclarée hors de 100 à 1 500")
    straddles_top = hi is None or hi > config.SIZE_MAX
    if straddles_top and li is not None and li > config.SIZE_MAX:
        return Fit(OUT, f"taille hors ICP ({label})", "bande à cheval sur 1 500, LinkedIn au-dessus")

    notes = []
    if lo < config.SIZE_MIN or straddles_top:
        notes.append(f"bande {band} à cheval sur la cible")
    if li is not None and hi is not None and li > hi:
        notes.append(f"LinkedIn ({li}) au-dessus de la bande")
    rule = "bande déclarée dans la cible" + (", " + " ; ".join(notes) if notes else "")
    note = f"taille à confirmer : {' ; '.join(notes)} ({li_txt})" if notes else ""
    return Fit(IN, f"taille dans l'ICP ({label})", rule, to_check=note)


def evaluate(row: pd.Series) -> IcpResult:
    sector = sector_fit(row["Industry"])
    geo, priority = geo_fit(row["country"], row["country_flag"], row["country_note"])
    size = size_fit(row["CompanySize"], row["EmployeesOnLinkedin"])
    return IcpResult(sector=sector, geo=geo, size=size, geo_priority=priority)
