import json
from pathlib import Path

import pytest

from app.agents.claude_client import ClaudeBadJson, FixtureClaudeClient
from app.agents.reader import (
    DEFAULT_FIXTURE,
    PROFILE_SCHEMA,
    Profile,
    ReaderError,
    fixture_for,
    read_business,
)

SELLERS = Path(__file__).parent / "fixtures" / "sellers"


def sample(name: str) -> dict:
    return json.loads((SELLERS / f"{name}.json").read_text(encoding="utf-8"))


class ScriptedClaude:
    """Returns (or raises) each scripted reply in turn; records what was asked."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list[dict] = []

    def ask_json(self, **kwargs):
        self.calls.append(kwargs)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


GOOD = {"name": "Test Shop", "tagline": "", "about": "", "area": "", "hours": "", "phone": "", "whatsapp": "",
        "upi_id": "", "tone": "friendly", "products": [{"name": "Thing", "price_inr": 100, "description": "", "category": "A"}]}


@pytest.mark.parametrize("name", ["meera_cakes", "tiffin_service", "tailor"])
def test_fixture_mode_reads_each_sample_seller(name):
    s = sample(name)
    claude = FixtureClaudeClient()
    profile = read_business(claude, description=s["description"], price_list=s["price_list"])
    assert claude.calls == [f"reader_{name}"]
    assert isinstance(profile, Profile) and profile.products


def test_meera_profile_has_her_prices():
    s = sample("meera_cakes")
    profile = read_business(FixtureClaudeClient(), description=s["description"], price_list=s["price_list"])
    prices = {p.price_inr for p in profile.products} | {o.price_inr for p in profile.products for o in p.options}
    assert {650, 1200, 550, 750, 1400, 420, 480} <= prices  # S21: ½ kg / 1 kg truffle cake are one item's two sizes


def test_unknown_input_falls_back_to_default_fixture():
    assert fixture_for("I sell handmade candles in Jaipur") == DEFAULT_FIXTURE


def test_one_call_strong_model_with_schema():
    claude = ScriptedClaude(GOOD)
    read_business(claude, description="I sell things", price_list="Thing - ₹100")
    assert len(claude.calls) == 1
    call = claude.calls[0]
    assert call["tier"] == "strong" and call["schema"] is PROFILE_SCHEMA
    assert "Thing - ₹100" in call["user"]


def test_retries_once_on_invalid_json():
    claude = ScriptedClaude(ClaudeBadJson("bad"), GOOD)
    assert read_business(claude, description="x").name == "Test Shop"
    assert len(claude.calls) == 2


def test_retries_once_on_schema_mismatch():
    claude = ScriptedClaude({"name": "No products"}, GOOD)
    assert read_business(claude, description="x").name == "Test Shop"


def test_gives_up_after_one_retry_with_plain_message():
    claude = ScriptedClaude(ClaudeBadJson("bad"), {"nope": 1}, GOOD)
    with pytest.raises(ReaderError) as e:
        read_business(claude, description="x")
    assert len(claude.calls) == 2
    assert str(e.value).startswith("Sorry, we couldn't read your business details")


def test_empty_input_is_rejected_without_a_call():
    claude = ScriptedClaude()
    with pytest.raises(ReaderError):
        read_business(claude, description="  ", price_list="")
    assert claude.calls == []


def test_image_is_sent_as_base64_image_block():
    claude = ScriptedClaude(GOOD)
    read_business(claude, description="My menu is in the photo", image=(b"\x89PNG fake", "image/png"))
    content = claude.calls[0]["user"]
    assert content[0]["type"] == "image"
    assert content[0]["source"] == {"type": "base64", "media_type": "image/png", "data": "iVBORyBmYWtl"}
    assert content[1]["type"] == "text"


def test_image_only_input_is_allowed():
    claude = ScriptedClaude(GOOD)
    read_business(claude, description="", image=(b"x", "image/jpeg"))
    assert len(claude.calls) == 1


@pytest.mark.parametrize("image", [(b"x", "application/pdf"), (b"x" * (5 * 1024 * 1024 + 1), "image/png")])
def test_bad_images_are_rejected_before_any_call(image):
    claude = ScriptedClaude()
    with pytest.raises(ReaderError):
        read_business(claude, description="x", image=image)
    assert claude.calls == []


def test_profile_normalises_prices_and_validates_contacts():
    p = Profile.model_validate({**GOOD, "products": [{"name": "A", "price_inr": "₹1,200"}]})
    assert p.products[0].price_inr == 1200 and p.products[0].category == "Menu"
    with pytest.raises(ValueError):
        Profile.model_validate({**GOOD, "whatsapp": "call me"})
    with pytest.raises(ValueError):
        Profile.model_validate({**GOOD, "upi_id": "not-a-upi"})
    assert Profile.model_validate({**GOOD, "upi_id": "meera.cakes@okaxis"}).upi_id == "meera.cakes@okaxis"
