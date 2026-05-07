"""Shared pytest fixtures."""
from pathlib import Path
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def tiny_gencon_path() -> Path:
    return FIXTURES / "tiny_gencon.xlsx"


@pytest.fixture
def tiny_bgg_path() -> Path:
    return FIXTURES / "tiny_bgg.csv"
