def predict_priority(text: str) -> str:
    """
    Simple NLP-based priority predictor.
    Later we will replace this with ML.
    """

    text = text.lower()

    critical_keywords = [
        "icu", "emergency", "power outage", "life threatening",
        "fire", "blood", "oxygen", "server down"
    ]

    high_keywords = [
        "urgent", "failure", "not working", "crash",
        "broken", "immediately"
    ]

    for word in critical_keywords:
        if word in text:
            return "critical"

    for word in high_keywords:
        if word in text:
            return "high"

    return "medium"

def predict_priority(description: str):
    text = description.lower()

    if "urgent" in text or "immediately" in text or "critical" in text:
        return "high"

    if "slow" in text or "sometimes" in text:
        return "medium"

    return "low"

