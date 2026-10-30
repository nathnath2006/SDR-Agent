"""L'export du cas n'est pas versionné : les tests qui en dépendent sont sautés s'il manque."""

from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1] / "data" / "mirakl_case_data.xlsx"


@pytest.fixture
def case_data() -> Path:
    if not DATA.exists():
        pytest.skip("data/mirakl_case_data.xlsx absent (export du cas non versionné)")
    return DATA
