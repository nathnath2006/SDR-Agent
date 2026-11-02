"""Couche sémantique (mode hybride) sur l'export du cas. Sautée si le modèle ne peut pas être chargé."""

from datetime import date

import pytest

from tamtam_agent import agent, config, semantic

from conftest import DATA

pytestmark = pytest.mark.skipif(not DATA.exists(), reason="export du cas non versionné")


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    try:
        semantic.preload()
    except Exception as exc:
        pytest.skip(f"modèle sémantique indisponible : {exc}")
    return agent.run(DATA, tmp_path_factory.mktemp("out"), provider="none", web=False, run_date=date(2026, 10, 29))


def _signal(result, account: str, fragment: str) -> dict:
    a = next(a for a in result.accounts if a["nom"] == account)
    return next(s for s in a["signaux"] if fragment in s["detail"])


def test_pixelforge_demoted_and_flagged(result):
    s = _signal(result, "PixelForge Studios", "E-commerce Strategist")
    assert s["role"] == config.ROLE_NOISE and s["reclasse"].startswith("rétrogradé")
    a = next(a for a in result.accounts if a["nom"] == "PixelForge Studios")
    assert any("à relire" in x for x in a["a_verifier"])


def test_rules_kept_where_model_is_unsure(result):
    # Le modèle rapproche ce texte de « postes commerciaux » : la règle (déclencheur) l'emporte.
    assert _signal(result, "Orbital Consumer Goods", "launch of a B2B marketplace")["role"] == config.ROLE_TRIGGER
    # Faux positif du modèle sous le seuil de promotion : reste du bruit.
    assert _signal(result, "PixelForge Studios", "e-commerce consulting")["role"] == config.ROLE_NOISE


def test_only_pixelforge_changes_on_the_export(result):
    changed = [s for a in result.accounts for s in a["signaux"] if s["reclasse"]]
    assert [s["event_id"] for s in changed] == ["E008"]
    assert sum(s["role"] == config.ROLE_TRIGGER for a in result.accounts for s in a["signaux"]) == 29


def test_rephrasings_are_caught():
    verdicts = semantic.classify([
        ("job_posting", "Nous recrutons un responsable des vendeurs partenaires pour notre place de marché"),
        ("news", "Va permettre à des marchands externes de vendre sur son site"),
        ("news", "Ouvre un nouveau bureau à Lyon"),
    ])
    assert [v.role for v in verdicts] == [config.ROLE_TRIGGER, config.ROLE_TRIGGER, config.ROLE_NOISE]
