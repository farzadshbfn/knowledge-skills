"""Tests for inline confidence tag validation."""

from validate_kb import check_confidence_tags
from learn_helpers import note


class TestCheckConfidenceTags:
    def test_no_tags_no_issues(self):
        files = {"topic/note.md": note()}
        assert check_confidence_tags(files) == []

    def test_valid_high_tag(self):
        content = note() + "\nSome claim. <conf:high>\n"
        files = {"topic/note.md": content}
        assert check_confidence_tags(files) == []

    def test_valid_medium_tag(self):
        content = note() + "\nSome claim. <conf:medium>\n"
        files = {"topic/note.md": content}
        assert check_confidence_tags(files) == []

    def test_low_tag_warns(self):
        content = note() + "\nShaky claim. <conf:low>\n"
        files = {"topic/note.md": content}
        issues = check_confidence_tags(files)
        assert len(issues) == 1
        assert issues[0].level == "warning"
        assert issues[0].check == "low_confidence"

    def test_malformed_tag_errors(self):
        content = note() + "\nBad claim. <conf:HIGH>\n"
        files = {"topic/note.md": content}
        issues = check_confidence_tags(files)
        assert len(issues) == 1
        assert issues[0].level == "error"
        assert issues[0].check == "invalid_conf_tag"

    def test_unknown_level_errors(self):
        content = note() + "\nWeird claim. <conf:maybe>\n"
        files = {"topic/note.md": content}
        issues = check_confidence_tags(files)
        assert len(issues) == 1
        assert issues[0].level == "error"
        assert issues[0].check == "invalid_conf_tag"

    def test_multiple_tags(self):
        content = note() + "\nClaim A. <conf:high>\nClaim B. <conf:low>\n"
        files = {"topic/note.md": content}
        issues = check_confidence_tags(files)
        assert len(issues) == 1  # only the low one warns
        assert issues[0].check == "low_confidence"

    def test_mixed_valid_and_malformed(self):
        content = note() + "\nClaim A. <conf:high>\nClaim B. <conf:MEDIUM>\n"
        files = {"topic/note.md": content}
        issues = check_confidence_tags(files)
        assert len(issues) == 1
        assert issues[0].level == "error"
        assert issues[0].check == "invalid_conf_tag"

    def test_skill_files_skipped(self):
        content = "---\nname: s\ndescription: d\n---\nText <conf:bad>\n"
        files = {"topic/skill/SKILL.md": content}
        assert check_confidence_tags(files) == []

    def test_index_files_skipped(self):
        content = "---\nname: i\ndescription: d\n---\nText <conf:bad>\n"
        files = {"topic/index.md": content}
        assert check_confidence_tags(files) == []
