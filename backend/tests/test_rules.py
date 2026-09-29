"""The deterministic triage rules (baseline + fallback layer)."""

import pytest

from app.ai.rules import DEFAULT_CATEGORIES, classify_category, classify_priority

CATS = [(name, keywords) for name, _desc, keywords, _team in DEFAULT_CATEGORIES]


@pytest.mark.parametrize(
    "text,expected",
    [
        # The P0 audit showed the old substring rules sending this to "General".
        ("I cannot log in to my payroll account", "Access & Identity"),
        ("VPN keeps dropping on home wifi", "Network & Connectivity"),
        ("Shared calendar invites are not arriving in my mailbox", "Email & Collaboration"),
        ("Suspicious phishing message, possible malware", "Security"),
        ("Where do I download my payslip?", "HR & Payroll"),
        ("The lights on floor 3 are out", "Facilities"),
        ("Please ignore the systems check email", "Email & Collaboration"),
        ("Something completely unrelated", "General"),
    ],
)
def test_category(text, expected):
    assert classify_category(text, CATS).value == expected


def test_whole_word_matching_only():
    # 'light' must not match inside 'highlight' (old substring bug).
    assert classify_category("Highlight colors in the report", CATS).value == "General"


def test_ties_go_to_the_earlier_category():
    # A known weakness of the rules baseline: 'outlook' (Software) and
    # 'calendar' (Email) score one hit each, and org order breaks the tie.
    # The ML router (P4/P5) is measured against exactly this kind of case.
    decision = classify_category("Outlook freezes when opening the calendar", CATS)
    assert decision.value == "Software & Applications"


def test_category_decision_is_explained():
    decision = classify_category("VPN and DNS problems on the network", CATS)
    assert decision.value == "Network & Connectivity"
    assert set(decision.matched) >= {"vpn", "dns", "network"}
    assert "matched" in decision.explain("category")


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Production down for everyone", "critical"),
        ("Urgent: I am locked out", "high"),
        ("Email is slow sometimes", "medium"),
        ("Can I get a second monitor?", "low"),
    ],
)
def test_priority(text, expected):
    assert classify_priority(text).value == expected


def test_unknown_org_taxonomy_falls_back_cleanly():
    assert classify_category("anything", [("Custom", ["foo"])]).value is None
