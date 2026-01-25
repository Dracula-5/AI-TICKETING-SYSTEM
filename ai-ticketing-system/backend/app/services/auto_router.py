def predict_category(text: str) -> str:
    text = text.lower()

    if any(word in text for word in ["power", "electric", "outage", "generator"]):
        return "ELECTRICAL"

    if any(word in text for word in ["network", "wifi", "server", "computer"]):
        return "IT_SUPPORT"

    if any(word in text for word in ["pipe", "water", "leak", "toilet"]):
        return "PLUMBING"

    if any(word in text for word in ["icu", "patient", "doctor", "medical"]):
        return "MEDICAL"

    if any(word in text for word in ["security", "theft", "camera"]):
        return "SECURITY"

    return "GENERAL"

def predict_category(title: str, description: str):
    text = f"{title} {description}".lower()

    if "wifi" in text or "network" in text or "internet" in text:
        return "Networking"

    if "light" in text or "electric" in text or "power" in text:
        return "Electrical"

    if "water" in text or "leak" in text or "pipe" in text:
        return "Plumbing"

    if "computer" in text or "system" in text or "software" in text:
        return "IT Support"

    return "General"

