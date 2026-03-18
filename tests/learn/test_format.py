"""Tests for output formatting."""

import json

from validate_kb import Issue, ValidationResult, format_json, format_text

class TestFormatText:
    def test_clean_kb(self):
        assert "coherent" in format_text(ValidationResult())

    def test_with_errors(self):
        result = ValidationResult(issues=[Issue("error", "broken_link", "a.md", "Broken link: b.md")])
        assert "errors" in format_text(result).lower()

    def test_quiet_mode(self):
        text = format_text(ValidationResult(), quiet=True)
        assert "Summary" not in text
        assert "coherent" in text

class TestFormatJson:
    def test_json_structure(self):
        result = ValidationResult(issues=[
            Issue("error", "broken_link", "a.md", "Broken"),
            Issue("warning", "orphan_note", "b.md", "Orphan"),
        ])
        data = json.loads(format_json(result))
        assert len(data["errors"]) == 1
        assert len(data["warnings"]) == 1
        assert "stats" in data
