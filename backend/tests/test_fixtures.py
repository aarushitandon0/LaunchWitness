import json
from pathlib import Path

import pytest

from app.agents.claude_client import FixtureClaudeClient
from app.agents.reader import Profile

SELLERS = Path(__file__).parent / "fixtures" / "sellers"


@pytest.mark.parametrize("name", ["meera_cakes", "tiffin_service", "tailor"])
def test_seller_fixture_shape(name):
    data = json.loads((SELLERS / f"{name}.json").read_text(encoding="utf-8"))
    assert data["id"] == name
    assert len(data["description"]) > 100
    lines = data["price_list"].splitlines()
    assert len(lines) >= 5
    assert sum("₹" in line for line in lines) >= 5


@pytest.mark.parametrize("name", ["meera_cakes", "tiffin_service", "tailor"])
def test_reader_fixture_is_a_valid_profile(name):
    out = FixtureClaudeClient().ask_json(fixture=f"reader_{name}", tier="strong", system="", user="")
    profile = Profile.model_validate(out)
    assert all(p.price_inr > 0 for p in profile.products)
    assert len({p.category for p in profile.products}) >= 2
