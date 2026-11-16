"""S10.5b copy rule: the landing page may only claim what the code does. Its schedule numbers are pinned here
to the monitor and renewal constants, so changing one without the other fails."""

from pathlib import Path

from app import renewals
from app.monitor import scheduler

LANDING = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "Landing.tsx").read_text(encoding="utf-8")


def test_quick_check_interval():
    assert scheduler.QUICK_MINUTES == 15 and "Every 15 minutes" in LANDING
    assert scheduler.QUICK_CHECKS == ["site_points", "https"]


def test_daily_checks_cover_what_the_page_says():
    daily = scheduler.daily_checks("sandbox")
    for name in ("site_points", "https", "email_mx", "email_spf", "email_dkim", "email_dmarc", "settings_match", "test_order"):
        assert name in daily
    assert "Every day" in LANDING and "a real test order goes through your order form" in LANDING


def test_recheck_and_alert_wording():
    assert scheduler.RECHECK_SECONDS == 60 and "We check again a minute later" in LANDING
    assert "once about that problem" in LANDING


def test_renewal_thresholds():
    assert renewals.THRESHOLDS == (30, 7, 1) and "30, 7 and 1 days ahead" in LANDING
    assert renewals.CERT_THRESHOLDS == (7, 1) and "with 7 days left" in LANDING and "again at 1 day" in LANDING


def test_no_jargon_in_the_main_watch_copy():
    main = LANDING.split("const WATCH", 1)[1].split("];", 1)[0]
    for word in ("MX", "DMARC", "SPF", "DKIM", "A record", "DNS"):
        assert word not in main, word
