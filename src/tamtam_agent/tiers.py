"""Paliers A / B / C / D (D9, D12), mesurés par rapport à la date d'extraction.

A : déclencheur ≤ 90 j + (amplificateur ≤ 180 j, ou déclencheurs de natures différentes)
B : déclencheur ≤ 90 j seul, ou déclencheur ≤ 180 j + amplificateur
C : amplificateurs sans déclencheur récent, ou déclencheur ancien / isolé (à creuser)
D : aucun signal exploitable
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import config

TIER_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "-": 4}
NATURE_LABELS = {"recrutement": "recrutement", "ouverture_vendeurs": "ouverture aux vendeurs tiers",
                 "dropship": "drop-ship", "acquisition": "acquisition",
                 "evolution": "évolution depuis l'analyse précédente"}


@dataclass
class TierResult:
    tier: str
    rule: str
    is_client: bool
    last_trigger: pd.Timestamp | None
    signals: list[dict] = field(default_factory=list)   # événements typés, plus récents d'abord

    @property
    def triggers(self) -> list[dict]:
        return [s for s in self.signals if s["role"] == config.ROLE_TRIGGER]

    @property
    def amplifiers(self) -> list[dict]:
        return [s for s in self.signals if s["role"] == config.ROLE_AMPLIFIER]


def assign_tier(group_events: pd.DataFrame, extraction_date: pd.Timestamp) -> TierResult:
    signals = []
    for row in group_events.sort_values("Date", ascending=False).itertuples():
        age = int((extraction_date - row.Date).days)
        signals.append({
            "event_id": row.EventId, "date": row.Date.date().isoformat(), "age_jours": age,
            "fenetre": _window(age), "type": row.Type, "detail": row.Detail,
            "libelle": row.libelle, "role": row.role,
            "nature": row.nature, "raison": row.raison, "confiance": row.confiance,
            "regle": row.regle, "origine": row.Origin,
        })

    is_client = any(s["role"] == config.ROLE_CLIENT for s in signals)
    triggers = [s for s in signals if s["role"] == config.ROLE_TRIGGER]
    last_trigger = pd.Timestamp(triggers[0]["date"]) if triggers else None
    if is_client:
        return TierResult("-", "Mirakl détecté : client, hors palier (D6)", True, last_trigger, signals)

    t_recent = [s for s in triggers if s["fenetre"] == "récent"]
    t_window = [s for s in triggers if s["fenetre"] in ("récent", "moyen")]
    a_window = [s for s in signals if s["role"] == config.ROLE_AMPLIFIER and s["fenetre"] in ("récent", "moyen")]
    natures = {s["nature"] for s in t_window}

    if t_recent and a_window:
        return TierResult("A", f"signal d'intention de moins de {config.WINDOW_RECENT_DAYS} jours, renforcé par "
                          f"un amplificateur ({a_window[0]['libelle']})", False,
                          last_trigger, signals)
    if t_recent and len(natures) > 1:
        kinds = " + ".join(NATURE_LABELS.get(n, n) for n in sorted(natures))
        return TierResult("A", f"signal d'intention de moins de {config.WINDOW_RECENT_DAYS} jours, confirmé par "
                          f"un signal d'une autre nature ({kinds})", False, last_trigger, signals)
    if t_recent:
        return TierResult("B", f"signal d'intention de moins de {config.WINDOW_RECENT_DAYS} jours, sans renfort",
                          False, last_trigger, signals)
    if t_window and a_window:
        return TierResult("B", f"signal d'intention de moins de {config.WINDOW_MAX_DAYS} jours, renforcé par "
                          f"un amplificateur ({a_window[0]['libelle']})", False,
                          last_trigger, signals)
    if t_window:
        return TierResult("C", f"signal d'intention de {t_window[0]['age_jours']} jours, sans renfort", False,
                          last_trigger, signals)
    if a_window:
        return TierResult("C", "contexte favorable (financement, croissance…) mais aucun signal d'intention",
                          False, last_trigger, signals)
    if triggers:
        return TierResult("C", f"signal d'intention ancien ({triggers[0]['age_jours']} jours) : à requalifier", False,
                          last_trigger, signals)
    return TierResult("D", f"aucun signal exploitable dans les {config.WINDOW_MAX_DAYS} derniers jours", False, None, signals)


def _window(age_days: int) -> str:
    if age_days <= config.WINDOW_RECENT_DAYS:
        return "récent"
    if age_days <= config.WINDOW_MAX_DAYS:
        return "moyen"
    return "ancien"
