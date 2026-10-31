"""Mémoire hebdomadaire (D14) et chemin LLM avec un faux fournisseur."""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from tamtam_agent import agent, config, memory, outputs
from tamtam_agent.llm import LLMClient, ResearchResult

from conftest import DATA as _DATA

pytestmark = pytest.mark.skipif(not _DATA.exists(), reason="export du cas non versionné")

DATA = Path(__file__).resolve().parents[1] / "data" / "mirakl_case_data.xlsx"


def _table(rows):
    return pd.DataFrame(rows, columns=["groupe_id", "compte", "statut", "palier", "raison"])


def test_memory_week_over_week():
    week1 = _table([(1, "A", "qualifié", "C", "r"), (2, "B", "qualifié", "B", "r"), (3, "C", "qualifié", "D", "r")])
    mem, _ = memory.update(week1, memory.load(Path("/nonexistent")), "2026-09-20", "2026-09-21")
    week2 = _table([(1, "A", "qualifié", "A", "r"), (2, "B", "qualifié", "C", "r"), (4, "D", "qualifié", "D", "r")])
    compared = memory.compare(week2, mem, "2026-09-27")
    assert compared.set_index("groupe_id")["evolution"].to_dict() == {1: "monté", 2: "baissé", 4: "nouveau"}
    new_mem, gone = memory.update(week2, mem, "2026-09-27", "2026-09-28")
    assert gone["groupe_id"].tolist() == [3]
    # Relancer sur la même extraction ne perd pas la comparaison.
    again = memory.compare(week2, new_mem, "2026-09-27")
    assert again["evolution"].tolist() == compared["evolution"].tolist()


class FakeLLM(LLMClient):
    """Faux fournisseur : traduit, rédige ; ne décide de rien."""
    provider = "fake"

    def __init__(self):
        super().__init__("fake-1")

    def _json(self, system, prompt, schema, effort):
        props = schema["properties"]
        if "labels" in props:
            return {"labels": [{"id": x["id"], "libelle": f"FR {x['texte']}"} for x in json.loads(prompt)]}
        if "accounts" in props:
            return {"accounts": [{"id": a["id"], "raison": f"raison {a['compte']}"} for a in json.loads(prompt)]}
        # Fiche : un axe sourcé, un axe à source inventée (doit être écarté).
        first_event = prompt.split("[E", 1)[1][:3]
        return {"pourquoi_maintenant": "signal récent", "ce_qui_a_change": "",
                "axes": [{"besoin": "?", "produit": "Catalog", "argument": "a", "sources": [f"E{first_event}"]},
                         {"besoin": "?", "produit": "Ads", "argument": "b", "sources": ["X99"]}],
                "a_verifier": []}

    def _research(self, system, prompt):
        return ResearchResult(text='{"marketplace": "aucune", "detail": "rien", "technologie": "", '
                                   '"anciennete": "", "sources": []}', sources=[])


def test_llm_writes_but_does_not_decide(tmp_path, monkeypatch):
    offline = agent.run(DATA, tmp_path / "off", provider="none", web=False, run_date=date(2026, 10, 29))
    fake = FakeLLM()
    monkeypatch.setattr(agent, "get_llm", lambda provider, cache_dir, api_key=None, model=None: fake)
    result = agent.run(DATA, tmp_path, provider="fake", web=True, run_date=date(2026, 10, 29))

    # Mêmes décisions qu'en mode règles seules.
    assert [(a["groupe_id"], a["statut"], a["palier"]) for a in result.accounts] == \
           [(a["groupe_id"], a["statut"], a["palier"]) for a in offline.accounts]
    assert result.explained and all(a["raison"].startswith("raison ") for a in result.accounts)
    assert all(s["libelle"].startswith("FR ") for a in result.accounts for s in a["signaux"])
    for a in result.top:
        assert [x["produit"] for x in a["pitch"]["axes"]] == ["Catalog"]   # axe non sourcé écarté
        assert a["verification_web"]["marketplace"] == "inconnu"            # « aucune » sans source refusé
    outputs.write_all(result, tmp_path)
    log_lines = (tmp_path / "runs" / result.run_id / "llm_log.jsonl").read_text().splitlines()
    assert {json.loads(x)["task"] for x in log_lines} >= {"translate_events", "write_pitch", "web_check", "write_reasons"}


def test_without_key_no_text(tmp_path):
    result = agent.run(DATA, tmp_path, provider="none", web=True, run_date=date(2026, 10, 29))
    assert not result.explained
    assert all(a["raison"] == "" and a["pitch"] is None and a["verification_web"] is None for a in result.accounts)
    assert len(result.top) == 20
