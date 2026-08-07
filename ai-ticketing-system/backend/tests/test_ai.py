"""
Tests for AI/NLP routing and priority prediction.
These run entirely in-process—no database or network required.
"""

import pytest
from app.ai.priority import predict_priority
from app.services.auto_router import predict_category


# ---------------------------------------------------------------------------
# Priority predictor
# ---------------------------------------------------------------------------

class TestPriorityPredictor:
    @pytest.mark.parametrize("text,expected", [
        ("patient in ICU needs oxygen immediately", "critical"),
        ("power outage on the entire floor", "critical"),
        ("server down and fire alarm triggered", "critical"),
        ("urgent: system crash, not working at all", "high"),
        ("broken pipe, need help immediately", "high"),
        ("printer is sometimes slow", "medium"),
        ("please update my profile picture", "low"),
        ("minor UI tweak requested", "low"),
    ])
    def test_keyword_classification(self, text, expected):
        assert predict_priority(text) == expected

    def test_case_insensitive(self):
        assert predict_priority("EMERGENCY Power Outage") == "critical"

    def test_returns_string(self):
        result = predict_priority("any random text here")
        assert isinstance(result, str)
        assert result in ("critical", "high", "medium", "low")


# ---------------------------------------------------------------------------
# Category predictor
# ---------------------------------------------------------------------------

class TestCategoryPredictor:
    @pytest.mark.parametrize("title,description,expected", [
        ("WiFi down", "no internet connection on floor 3", "IT Support"),
        ("Light not working", "electrical fault in corridor", "Electrical"),
        ("Water pipe burst", "leak flooding the basement", "Plumbing"),
        ("Random request", "nothing specific here", "General"),
        ("Network switch failed", "server unreachable", "IT Support"),
        ("Generator overload", "power keeps tripping", "Electrical"),
        ("Doctor needed", "ICU patient deteriorating", "Medical"),
        ("Security breach", "camera footage missing", "Security"),
    ])
    def test_category_routing(self, title, description, expected):
        assert predict_category(title, description) == expected

    def test_title_only_works(self):
        result = predict_category("broken pipe")
        assert result == "Plumbing"

    def test_returns_string(self):
        result = predict_category("", "")
        assert isinstance(result, str)

    def test_unknown_defaults_to_general(self):
        assert predict_category("unrelated topic", "nothing matches") == "General"
