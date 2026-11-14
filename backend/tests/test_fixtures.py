import json
from pathlib import Path

import pytest

from app.agents.claude_client import FixtureClaudeClient

SELLERS = Path(__file__).parent / "fixtures" / "sellers"


@pytest.mark.parametrize("name", ["meera_cakes", "tiffin_service", "tailor"])
def test_seller_fixture_shape(name):
    data = json.loads((SELLERS / f"{name}.json").read_text(encoding="utf-8"))
    assert data["id"] == name
    assert len(data["description"]) > 100
    lines = data["price_list"].splitlines()
    assert len(lines) >= 5
    assert sum("₹" in line for line in lines) >= 5


def test_reader_fixture_loads_by_default():
    out = FixtureClaudeClient().ask_json(fixture="reader_meera_cakes", tier="strong", system="", user="")
    assert out["business_name"] == "Meera's Home Cakes"
    assert all(p["price_inr"] > 0 for p in out["products"])
