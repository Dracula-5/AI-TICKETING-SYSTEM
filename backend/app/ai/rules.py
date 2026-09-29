"""
Deterministic triage rules — the measured baseline and the fallback/safety
layer beneath the ML models added in P4/P5. This is keyword matching, not a
learned model, and the UI labels its output as "Rules engine".

Differences from the original keyword rules this replaces:
  * whole-word/phrase matching (the old substring test matched `light` inside
    `highlight` and `system` inside `systems`),
  * scores every category instead of taking the first match,
  * keywords live on each organization's categories, so they are configurable,
  * returns the matched terms, so every decision can be explained.
"""

import re
from dataclasses import dataclass, field

PRIORITIES = ("low", "medium", "high", "critical")

# Priority rules are evaluated highest-first; the first tier with a match wins.
PRIORITY_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "critical",
        (
            "outage",
            "production down",
            "site down",
            "server down",
            "all users",
            "everyone",
            "data loss",
            "ransomware",
            "security breach",
            "breach",
            "compromised",
            "cannot process payments",
        ),
    ),
    (
        "high",
        (
            "urgent",
            "asap",
            "blocked",
            "cannot work",
            "can't work",
            "unable to work",
            "not working",
            "failed",
            "failure",
            "crash",
            "crashes",
            "error",
            "locked out",
            "deadline",
        ),
    ),
    ("medium", ("slow", "intermittent", "sometimes", "degraded", "delay", "delayed")),
]

# Default taxonomy for new organizations: (name, description, keywords, default team name).
DEFAULT_CATEGORIES: list[tuple[str, str, list[str], str]] = [
    (
        "Access & Identity",
        "Logins, passwords, MFA, permissions",
        [
            "password",
            "login",
            "log in",
            "sign in",
            "mfa",
            "2fa",
            "locked out",
            "access",
            "permission",
            "sso",
            "account",
        ],
        "Service Desk",
    ),
    (
        "Network & Connectivity",
        "VPN, Wi-Fi, internet, DNS",
        ["vpn", "wifi", "wi-fi", "network", "internet", "dns", "connection", "connectivity", "latency", "firewall"],
        "Infrastructure",
    ),
    (
        "Hardware",
        "Laptops, monitors, printers, peripherals",
        ["laptop", "monitor", "printer", "keyboard", "mouse", "hardware", "screen", "battery", "docking", "headset"],
        "Service Desk",
    ),
    (
        "Software & Applications",
        "Installs, licenses, application errors",
        [
            "install",
            "software",
            "application",
            "app",
            "license",
            "update",
            "upgrade",
            "excel",
            "outlook",
            "crash",
            "bug",
        ],
        "Applications",
    ),
    (
        "Email & Collaboration",
        "Email, calendar, chat, file sharing",
        ["email", "e-mail", "mailbox", "calendar", "teams", "slack", "zoom", "sharepoint", "onedrive", "meeting"],
        "Applications",
    ),
    (
        "Security",
        "Phishing, malware, suspicious activity",
        ["phishing", "malware", "virus", "suspicious", "security", "breach", "ransomware", "spam", "compromised"],
        "Security",
    ),
    (
        "HR & Payroll",
        "Payslips, leave, onboarding",
        ["payroll", "payslip", "salary", "leave", "onboarding", "offboarding", "benefits", "hr", "reimbursement"],
        "People Operations",
    ),
    (
        "Facilities",
        "Office, access cards, desks, building",
        [
            "office",
            "desk",
            "badge",
            "access card",
            "parking",
            "air conditioning",
            "light",
            "lights",
            "building",
            "room",
        ],
        "Facilities",
    ),
    ("General", "Anything that does not fit another category", [], "Service Desk"),
]

DEFAULT_TEAMS: list[tuple[str, str]] = [
    ("Service Desk", "First-line support and triage"),
    ("Infrastructure", "Network, servers and connectivity"),
    ("Applications", "Business applications and collaboration tools"),
    ("Security", "Security operations"),
    ("People Operations", "HR and payroll requests"),
    ("Facilities", "Workplace and building services"),
]

FALLBACK_CATEGORY = "General"


@dataclass
class RuleDecision:
    value: str | None
    matched: list[str] = field(default_factory=list)

    def explain(self, label: str) -> str:
        if not self.matched:
            return f"{label}={self.value} (no keyword matched; default)"
        return f"{label}={self.value} (matched: {', '.join(repr(m) for m in self.matched)})"


def _compile(term: str) -> re.Pattern:
    return re.compile(r"(?<![\w-])" + re.escape(term.lower()) + r"(?![\w-])")


def _matches(text: str, terms) -> list[str]:
    return [t for t in terms if _compile(t).search(text)]


def classify_priority(text: str) -> RuleDecision:
    lowered = text.lower()
    for level, terms in PRIORITY_RULES:
        hits = _matches(lowered, terms)
        if hits:
            return RuleDecision(level, hits)
    return RuleDecision("low")


def classify_category(text: str, categories: list[tuple[str, list[str]]]) -> RuleDecision:
    """`categories` is [(name, keywords), ...] in the org's display order."""
    lowered = text.lower()
    best: RuleDecision | None = None
    for name, keywords in categories:
        hits = _matches(lowered, keywords or [])
        if hits and (best is None or len(hits) > len(best.matched)):
            best = RuleDecision(name, hits)
    if best:
        return best
    names = [n for n, _ in categories]
    return RuleDecision(FALLBACK_CATEGORY if FALLBACK_CATEGORY in names else None)
