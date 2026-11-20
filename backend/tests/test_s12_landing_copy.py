"""S12: the interactive landing sections may only say what the code does. Every "If it breaks here" sentence, fix and
play-through step is pinned here to the checker, the playbook, the Doctor's code-written steps and the monitor."""

import re
from pathlib import Path

import pytest

from app import incidents
from app.agents import checker, investigator
from app.agents.playbook import fixes_for
from app.monitor import scheduler

SRC = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "LandingProof.tsx").read_text(encoding="utf-8")
CHECKER = Path(checker.__file__).read_text(encoding="utf-8")
HOP_CHECK = {"Address": "site_points", "Secure page": "https", "Your shop": "https", "Order form": "test_order",
             "Mail server": "test_order", "Your inbox": "test_order"}


def hops() -> list[dict]:
    block = SRC.split("export const HOP_INFO", 1)[1].split("];", 1)[0]
    out = []
    for chunk in block.split("    name: ")[1:]:
        def field(k: str, chunk=chunk) -> str | None:
            m = re.search(rf'\b{k}:\s*"((?:[^"\\]|\\.)*)"', chunk)
            return m.group(1) if m else None
        out.append({"name": chunk.split('"')[1], "see": field("see"), "fix": field("fix"), "doctor": field("doctor"),
                    "needs": "needsYou: true" in chunk})
    return out


def test_six_hops_in_the_order_the_checker_proves_them():
    assert [h["name"] for h in hops()] == list(HOP_CHECK)


@pytest.mark.parametrize("hop", hops(), ids=lambda h: h["name"])
def test_each_hop_breaks_with_the_real_words_and_the_real_fix(hop):
    check = HOP_CHECK[hop["name"]]
    assert f'"{hop["see"]}"' in CHECKER  # the checker's own sentence for this failure
    if hop["fix"]:
        assert not hop["needs"]
        assert hop["fix"] in fixes_for(check, "sandbox")  # a fix the playbook really allows on a shop like this
        assert hop["doctor"] == incidents.FIX_WORDS[hop["fix"]]
    else:
        assert hop["needs"] and not fixes_for(check, "sandbox")
        # the exact steps the code writes for this failure (or the opening of them)
        written = investigator.next_step(check, "sandbox", hop["see"])
        if "mail server" in hop["name"].lower():
            written = investigator.MAIL_SIGN_IN_REFUSED
        assert written.startswith(hop["doctor"].replace("“", "“").replace("”", "”")), hop["name"]


def test_the_inbox_hop_is_proven_only_by_the_owner():
    assert "Proven when you tap “Yes, I got it”" in SRC and "proven when you tap" in SRC


def test_examples_are_labelled():
    assert SRC.count("Example") >= 3


def test_watch_day_matches_the_monitor():
    assert scheduler.QUICK_MINUTES == 15 and "const TICKS = 96" in SRC  # 24 h / 15 min
    assert scheduler.RECHECK_SECONDS == 60 and "We check again a minute later" in SRC
    assert scheduler.QUICK_CHECKS == ["site_points", "https"]
    assert "your address still leads to your shop, and it opens securely" in SRC
    steps = SRC.split("export const BREAK_STEPS", 1)[1].split("];", 1)[0]
    assert "Looked up where your address leads → it leads nowhere" in steps
    assert incidents.FIX_WORDS["repoint_site"] in steps and "Checked again: working" in steps
    # an email only for what is still broken after the fix, once per problem (scheduler.check_alert)
    assert "No email this time" in steps and "one email about it, and no more about that problem" in steps


def test_play_through_uses_the_same_look_words_as_the_report():
    assert "Looked up where your address leads" == incidents.LOOK_WORDS["resolve"]


def test_demo_strip_sits_between_the_proof_and_the_watch_sections():
    """S21: the demo strip goes after "How the proof works" and before "We keep watching"; the sections the owner
    called done keep their order."""
    landing = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "Landing.tsx").read_text(encoding="utf-8")
    order = [landing.index(f'id="{x}"') for x in ("how", "proof", "demos", "watch", "check", "security")]
    assert order == sorted(order)
