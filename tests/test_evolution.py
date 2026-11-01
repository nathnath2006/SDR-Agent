"""Option évolutions : un export plus ancien, puis l'export du cas avec la comparaison."""

import json
from datetime import date

import pandas as pd
import pytest

from tamtam_agent import agent, config, evolution
from tamtam_agent.llm import LLMClient

from conftest import DATA

pytestmark = pytest.mark.skipif(not DATA.exists(), reason="export du cas non versionné")
CUTOFF = pd.Timestamp("2026-08-01")


class EvolutionLLM(LLMClient):
    """Juge « nette » chaque compte en citant son premier signal nouveau, sauf un qui cite un identifiant inventé."""
    provider = "fake"

    def __init__(self):
        super().__init__("fake-1")
        self.seen: list[dict] = []

    def _json(self, system, prompt, schema, effort):
        props = schema["properties"]
        if "comptes" in props:
            items = json.loads(prompt)
            first = not self.seen
            self.seen += items
            return {"comptes": [{"id": x["id"], "verdict": "nette", "explication": "pas de plus",
                                 "sources": ["X99"] if first and i == 0 else [x["signaux_nouveaux"][0][1:5]],
                                 "confiance": "moyenne"} for i, x in enumerate(items)]}
        if "labels" in props:
            return {"labels": [{"id": x["id"], "libelle": x["texte"]} for x in json.loads(prompt)]}
        if "accounts" in props:
            return {"accounts": []}
        return {"pourquoi_maintenant": "", "ce_qui_a_change": "", "axes": [], "a_verifier": []}

    def _research(self, system, prompt):
        raise NotImplementedError


def _older_export(tmp_path):
    """L'export du cas, amputé des événements postérieurs au 1er août 2026."""
    sheets = pd.read_excel(DATA, sheet_name=None)
    sheets["events"] = sheets["events"][pd.to_datetime(sheets["events"]["Date"]) < CUTOFF]
    path = tmp_path / "ancien.xlsx"
    with pd.ExcelWriter(path) as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)
    return path


def test_evolution_becomes_a_trigger(tmp_path, monkeypatch):
    from tamtam_agent import outputs
    out = tmp_path / "out"
    old = agent.run(_older_export(tmp_path), out, provider="none", web=False, run_date=date(2026, 8, 2))
    outputs.write_all(old, out)
    without = agent.run(DATA, tmp_path / "seul", provider="none", web=False, run_date=date(2026, 10, 29))

    fake = EvolutionLLM()
    monkeypatch.setattr(agent, "get_llm", lambda provider, cache_dir, api_key=None, model=None: fake)
    result = agent.run(DATA, out, provider="fake", web=False, run_date=date(2026, 10, 29), evolution=True)

    assert result.evolution["base"] == old.run_id and result.evolution["evalues"] == len(fake.seen) > 0
    # Seuls les signaux apparus depuis l'ancien export sont présentés comme nouveaux.
    assert all(line.split(" ")[1] >= CUTOFF.date().isoformat() for x in fake.seen for line in x["signaux_nouveaux"])

    by_id = {a["groupe_id"]: a for a in result.accounts}
    before = {a["groupe_id"]: a for a in without.accounts}
    refused = int(fake.seen[0]["id"])
    assert by_id[refused]["evolution_mp"]["verdict"] == "aucune"           # source inventée : refusée
    assert not any(s["event_id"] == evolution.EVENT_ID for s in by_id[refused]["signaux"])
    judged = [int(x["id"]) for x in fake.seen[1:]]
    for gid in judged:
        a = by_id[gid]
        evo_signal = next(s for s in a["signaux"] if s["event_id"] == evolution.EVENT_ID)
        assert evo_signal["role"] == config.ROLE_TRIGGER
        if not a["liste"] == config.LIST_CLIENTS:
            assert "ABCD".index(a["palier"]) <= "ABCD".index(before[gid]["palier"])   # jamais rétrogradé

    # Même export que la base : rien de nouveau, aucun appel.
    fake.seen.clear()
    monkeypatch.setattr(evolution, "previous_run", lambda runs_dir, extraction: evolution.Base(
        "x", "2026-09-20", [outputs.explanation(a) for a in without.accounts]))
    again = agent.run(DATA, out, provider="fake", web=False, run_date=date(2026, 10, 29), evolution=True)
    assert fake.seen == [] and again.evolution["evalues"] == 0
