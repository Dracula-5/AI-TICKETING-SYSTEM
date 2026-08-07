_CATEGORY_RULES = [
    (["wifi", "network", "internet", "server", "computer", "software", "system"], "IT Support"),
    (["light", "electric", "power", "outage", "generator"], "Electrical"),
    (["water", "leak", "pipe", "toilet", "plumb"], "Plumbing"),
    (["icu", "patient", "doctor", "medical", "hospital"], "Medical"),
    (["security", "theft", "camera", "guard"], "Security"),
]


def predict_category(title: str, description: str = "") -> str:
    """
    Rule-based intent classifier for ticket routing.
    Combines title + description, matches keyword lists in priority order.
    Returns a human-readable category string used to route the ticket to the
    right team.  Designed as a drop-in replacement for an ML classifier so the
    signature stays stable when a trained model is substituted later.
    """
    text = f"{title} {description}".lower()
    for keywords, category in _CATEGORY_RULES:
        if any(kw in text for kw in keywords):
            return category
    return "General"

