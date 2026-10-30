"""Chargement de l'export Excel (même format chaque semaine)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

REQUIRED_SHEETS = ("tamtam_prospects", "events", "crm_mirakl_accounts")
PROSPECT_COLUMNS = (
    "Id", "Name", "Website", "Country", "Activity", "Industry", "CompanySize",
    "EmployeesOnLinkedin", "Revenue", "Countries", "Strategy", "E-commerce in Strat",
)
EVENT_COLUMNS = ("AccountId", "AccountName", "Type", "Date", "Detail")


@dataclass
class CaseData:
    prospects: pd.DataFrame
    events: pd.DataFrame
    crm: pd.DataFrame
    source: Path

    @property
    def orphan_events(self) -> pd.DataFrame:
        """Événements dont le compte n'existe pas dans les prospects."""
        return self.events[~self.events["AccountId"].isin(self.prospects["Id"])]

    @property
    def extraction_date(self) -> pd.Timestamp:
        """Date d'extraction = date du dernier événement (D12)."""
        return self.events["Date"].max()


def load_case_data(path: str | Path) -> CaseData:
    path = Path(path)
    sheets = pd.read_excel(path, sheet_name=None)
    missing = [s for s in REQUIRED_SHEETS if s not in sheets]
    if missing:
        raise ValueError(f"Onglets manquants dans {path.name} : {missing}")

    prospects = _clean_sheet(sheets["tamtam_prospects"], PROSPECT_COLUMNS, "tamtam_prospects", "Id")
    events = _clean_sheet(sheets["events"], EVENT_COLUMNS, "events", "AccountId")

    # "-" signifie "non renseigné" dans l'export Tamtam.
    prospects = prospects.replace({"-": pd.NA})
    prospects["Id"] = prospects["Id"].astype("int64")

    events["AccountId"] = events["AccountId"].astype("int64")
    events["Date"] = pd.to_datetime(events["Date"], errors="coerce")
    events = events[events["Date"].notna()].reset_index(drop=True)
    events.insert(0, "EventId", [f"E{i + 1:03d}" for i in range(len(events))])

    return CaseData(prospects=prospects, events=events, crm=sheets["crm_mirakl_accounts"], source=path)


def _clean_sheet(df: pd.DataFrame, expected: tuple[str, ...], sheet: str, key: str) -> pd.DataFrame:
    """Garde les colonnes de l'export et les lignes qui ont une clé : ignore ce qu'un humain
    a pu ajouter à côté (tableau croisé, colonnes sans nom, lignes vides)."""
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise ValueError(f"Colonnes manquantes dans {sheet} : {missing}")
    df = df[[c for c in df.columns if not str(c).startswith("Unnamed")]]
    df = df[pd.to_numeric(df[key], errors="coerce").notna()]
    return df.reset_index(drop=True)
