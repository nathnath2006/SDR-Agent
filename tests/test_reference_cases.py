"""Jeu de référence du handoff (section 6), en mode hors ligne (règles seules)."""

from datetime import date
from pathlib import Path

import pytest

from tamtam_agent import agent, config, icp
from tamtam_agent.clean import country_check
from tamtam_agent.signals import classify_by_rules

DATA = Path(__file__).resolve().parents[1] / "data" / "mirakl_case_data.xlsx"


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    if not DATA.exists():
        pytest.skip("export du cas non versionné")
    out = tmp_path_factory.mktemp("out")
    return agent.run(DATA, out, provider="none", web=False, run_date=date(2026, 10, 29))


@pytest.fixture(scope="module")
def by_name(result):
    def find(fragment: str) -> dict:
        matches = [a for a in result.accounts if any(fragment.lower() in e.lower() for e in a["entites"])]
        assert len(matches) == 1, f"{fragment} : {len(matches)} groupes trouvés"
        return matches[0]
    return find


def test_reference_counts(result):
    triggers = [s for a in result.accounts for s in a["signaux"] if s["role"] == config.ROLE_TRIGGER]
    groups = {a["groupe_id"] for a in result.accounts if any(s["role"] == config.ROLE_TRIGGER for s in a["signaux"])}
    assert len(triggers) == 30
    assert len(groups) == 23            # 24 comptes du handoff, Verdalis fusionné
    recent = [a for a in result.accounts
              if any(s["role"] == config.ROLE_TRIGGER and s["fenetre"] == "récent" for s in a["signaux"])]
    assert len(recent) == 17            # 18 comptes du handoff, Verdalis fusionné


def test_fintorra_out_of_icp_but_watched(by_name, result):
    a = by_name("Fintorra")
    assert a["statut"] == config.STATUS_DISQUALIFIED
    assert a["liste"] == config.LIST_WATCH
    assert a not in result.top


def test_tennis_point_funding_alone_is_c(by_name):
    assert by_name("Tennis-Point")["palier"] == "C"


@pytest.mark.parametrize("name", ["babymarkt.de", "AMOR Group", "Land O'Lakes"])
def test_mirakl_clients(by_name, name):
    a = by_name(name)
    assert a["liste"] == config.LIST_CLIENTS
    assert a["statut"] == config.STATUS_DISQUALIFIED


@pytest.mark.parametrize("name", ["refurbed", "INTERSPORT Austria", "Ben E. Keith"])
def test_vtex_is_context_not_trigger(by_name, name):
    a = by_name(name)
    vtex = [s for s in a["signaux"] if "VTEX" in s["detail"]]
    assert vtex and all(s["role"] == config.ROLE_CONTEXT for s in vtex)
    assert a["palier"] not in ("A", "B")


def test_orbital_tier_a_size_to_check(by_name, result):
    # Règle du 2026-10-29 : bande 1001-5000 + 1 200 profils = qualifié, taille à confirmer.
    a = by_name("Orbital Consumer Goods")
    assert a["palier"] == "A"
    assert a["statut"] == config.STATUS_QUALIFIED
    assert any("1001-5000" in n for n in a["a_verifier"])
    assert a in result.top


def test_verdalis_single_group_with_spanish_signal(by_name):
    a = by_name("Verdalis Retail España")
    assert a["nom"] == "Verdalis Retail Group"
    assert len(a["entites"]) == 3
    assert any("Verdalis Retail España" in s["origine"] for s in a["signaux"])


def test_klarion_merged_with_both_strategies(by_name):
    a = by_name("Klarion Distribution SAS")
    assert len(a["entites"]) == 2
    assert len(a["strategies"]) == 2
    assert any(s["role"] == config.ROLE_TRIGGER and "E-commerce Director" in s["detail"] for s in a["signaux"])


def test_hugendubel_merge_explained(by_name):
    a = by_name("Hugendubel")
    assert len(a["entites"]) == 2
    assert "doublon" in a["fusion"]


@pytest.mark.parametrize("name", ["PixelForge Studios", "Boulangerie Ferrand", "Global Steel Corp"])
def test_out_of_icp(by_name, name):
    assert by_name(name)["statut"] == config.STATUS_DISQUALIFIED


def test_pearl_suspect_country_to_dig(by_name):
    a = by_name("PEARL. GmbH")
    assert a["statut"] == config.STATUS_DIG
    assert "Botswana" in a["pays_note"]
    assert a["palier"] in ("A", "B")


def test_winsupply_acquisition_is_trigger(by_name):
    a = by_name("Winsupply")
    assert any(s["role"] == config.ROLE_TRIGGER and s["nature"] == "acquisition" for s in a["signaux"])


def test_top20_a_then_b_then_best_c(result):
    assert len(result.top) == config.TOP_N
    assert all(a["statut"] != config.STATUS_DISQUALIFIED for a in result.top)
    tiers = [a["palier"] for a in result.top]
    assert tiers == sorted(tiers) and tiers.count("A") == 5 and tiers.count("B") == 7
    c = [a for a in result.top if a["palier"] == "C"]
    assert all(a["a_qualifier"] for a in c)
    assert [a["dernier_signal"] for a in c] == sorted((a["dernier_signal"] for a in c), reverse=True)


def test_same_export_same_top20(tmp_path, case_data):
    runs = [agent.run(DATA, tmp_path / str(i), provider="none", web=False, run_date=date(2026, 10, 29))
            for i in range(2)]
    assert [a["groupe_id"] for a in runs[0].top] == [a["groupe_id"] for a in runs[1].top]


def test_group_left_separate(tmp_path, case_data):
    result = agent.run(DATA, tmp_path, provider="none", web=False, run_date=date(2026, 10, 29),
                       group_decisions={"9934690-10194311": False})
    assert sum(a["nom"] == "Hugendubel" for a in result.accounts) == 2


# --- Règles unitaires ----------------------------------------------------------
@pytest.mark.parametrize("band, linkedin, level", [
    ("201-500", 300, icp.IN),
    ("201-500", 40, icp.IN),             # LinkedIn = plancher : pas de contradiction
    ("51-200", 60, icp.IN),              # bande à cheval : qualifié, à vérifier
    ("501-1000", 1800, icp.IN),          # bande dans la cible : elle l'emporte sur LinkedIn
    ("51-200", 1200, icp.IN),            # incohérence, mais tout reste dans la cible
    ("1001-5000", 133, icp.IN),          # cas ANWR
    ("1001-5000", 1634, icp.OUT),        # LinkedIn sous-estime : > 1 500 suffit
    ("5001-10,000", 400, icp.OUT),
    ("11-50", 40, icp.OUT),
    ("11-50", 150, icp.OUT),             # la bande déclarée l'emporte
    (None, 300, icp.IN),
    (None, None, icp.UNCERTAIN),
])
def test_size_fit(band, linkedin, level):
    assert icp.size_fit(band, linkedin).level == level


def test_legal_form_case_sensitive():
    assert country_check("Ag Processing Inc", "https://agp.com", "United States")["country_flag"] == "ok"
    assert country_check("PEARL. GmbH", "https://pearl.de", "Botswana")["country_flag"] == "suspect"


@pytest.mark.parametrize("etype, detail, role", [
    ("job_posting", "Opening 6 Sales roles (SDR + AE)", config.ROLE_CONTEXT),
    ("job_posting", "Hiring a Data Engineer", config.ROLE_AMPLIFIER),
    ("job_posting", "Hiring a Head of Digital Commerce", config.ROLE_TRIGGER),
    ("leadership_change", "Appoints a new CFO", config.ROLE_CONTEXT),
    ("linkedin_growth", "Headcount +8% over 6 months, mostly store staff", config.ROLE_CONTEXT),
    ("news", "Marketplace powered by Mirakl celebrates its first anniversary", config.ROLE_CLIENT),
    ("news", "Sponsors a regional sports event", config.ROLE_NOISE),
])
def test_rules(etype, detail, role):
    assert classify_by_rules(etype, detail)["role"] == role
