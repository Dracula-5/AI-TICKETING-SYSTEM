def predict_priority(text: str) -> str:
    """
    Simple NLP-based priority predictor.
    Can be replaced later with ML model.
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

    medium_keywords = [
        "slow", "sometimes"
    ]

    for word in critical_keywords:
        if word in text:
            return "critical"

    for word in high_keywords:
        if word in text:
            return "high"

    for word in medium_keywords:
        if word in text:
            return "medium"

    return "low"
