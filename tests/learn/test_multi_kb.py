"""Tests for multi-KB validation, cross-KB links, changelog, and path exclusivity."""

import sys
from pathlib import Path
from unittest import mock

from validate_kb import (
    KBConfig, KBEntry, MockFileSystem,
    check_changelog, check_cross_kb_escape, check_cross_kb_links,
    check_kb_path_exclusivity, main, validate_multi_kb,
)
from learn_helpers import note, index

class TestCheckChangelog:
    def test_no_changes(self):
        assert check_changelog([], "knowledge") == []

    def test_topic_md_changes_with_changelog(self):
        changed = ["knowledge/topic/note.md", "knowledge/CHANGELOG.md"]
        assert check_changelog(changed, "knowledge") == []

    def test_topic_md_changes_without_changelog(self):
        changed = ["knowledge/topic/note.md"]
        issues = check_changelog(changed, "knowledge")
        assert len(issues) == 1
        assert issues[0].check == "missing_changelog"

    def test_non_md_changes_ignored(self):
        assert check_changelog(["knowledge/topic/skill/scripts/validate_kb.py"], "knowledge") == []

    def test_changes_outside_topics(self):
        assert check_changelog([".claude/skills/kb-learn/SKILL.md"], "knowledge") == []

    def test_dotslash_kb_root_matches_git_paths(self):
        issues = check_changelog(["knowledge/topic/note.md"], "./knowledge")
        assert len(issues) == 1
        assert issues[0].check == "missing_changelog"

    def test_dotslash_changelog_detected(self):
        changed = ["knowledge/topic/note.md", "knowledge/CHANGELOG.md"]
        assert check_changelog(changed, "./knowledge") == []

class TestMainChangelog:
    def test_main_reports_missing_changelog(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        kb = tmp_path / "knowledge" 
        kb.mkdir(parents=True)
        (kb / "index.md").write_text("---\nname: Root\ndescription: Root.\n---\n")

        with mock.patch("validate_kb._get_git_changed_files", return_value=["knowledge/index.md"]):
            assert main(["knowledge"]) == 1
        assert "missing_changelog" in capsys.readouterr().out

    def test_main_passes_when_changelog_present(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        kb = tmp_path / "knowledge" 
        kb.mkdir(parents=True)
        (kb / "index.md").write_text("---\nname: Root\ndescription: Root.\n---\n")

        with mock.patch("validate_kb._get_git_changed_files",
                        return_value=["knowledge/index.md", "knowledge/CHANGELOG.md"]):
            assert main(["knowledge"]) == 0

    def test_main_no_changelog_check_without_git(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        kb = tmp_path / "knowledge" 
        kb.mkdir(parents=True)
        (kb / "index.md").write_text("---\nname: Root\ndescription: Root.\n---\n")

        with mock.patch("validate_kb._get_git_changed_files", return_value=[]):
            assert main(["knowledge"]) == 0

class TestKBPathExclusivity:
    def test_no_overlap(self):
        config = KBConfig(entries=[KBEntry("core", "./knowledge"), KBEntry("ios", "./ios/knowledge")])
        assert check_kb_path_exclusivity(config) == []

    def test_nested_paths_error(self):
        config = KBConfig(entries=[KBEntry("core", "./knowledge"), KBEntry("sub", "./knowledge/sub")])
        issues = check_kb_path_exclusivity(config)
        assert len(issues) == 1
        assert issues[0].check == "nested_kb_paths"

    def test_identical_paths_error(self):
        config = KBConfig(entries=[KBEntry("a", "./knowledge"), KBEntry("b", "./knowledge")])
        assert len(check_kb_path_exclusivity(config)) == 1

    def test_similar_prefix_not_nested(self):
        config = KBConfig(entries=[KBEntry("core", "./knowledge"), KBEntry("extra", "./knowledge-extra")])
        assert check_kb_path_exclusivity(config) == []

class TestCrossKBLinks:
    def test_valid_cross_kb_link(self):
        config = KBConfig(entries=[KBEntry("core", "./kb1"), KBEntry("ios", "./kb2")])
        kb_file_maps = {
            "core": {"topic/note.md": "See [@ios/topic/other.md](@ios/topic/other.md)."},
            "ios": {"topic/other.md": note("Other")},
        }
        assert check_cross_kb_links(config, kb_file_maps) == []

    def test_unknown_kb_name(self):
        config = KBConfig(entries=[KBEntry("core", "./kb1")])
        kb_file_maps = {"core": {"topic/note.md": "See [@nonexistent/note.md](@nonexistent/note.md)."}}
        issues = check_cross_kb_links(config, kb_file_maps)
        assert len(issues) == 1
        assert issues[0].check == "unknown_cross_kb"

    def test_broken_target_path(self):
        config = KBConfig(entries=[KBEntry("core", "./kb1"), KBEntry("ios", "./kb2")])
        kb_file_maps = {
            "core": {"topic/note.md": "See [@ios/missing.md](@ios/missing.md)."},
            "ios": {"topic/other.md": note("Other")},
        }
        issues = check_cross_kb_links(config, kb_file_maps)
        assert len(issues) == 1
        assert issues[0].check == "broken_cross_kb_link"

    def test_no_cross_kb_links(self):
        config = KBConfig(entries=[KBEntry("core", "./kb")])
        kb_file_maps = {"core": {"topic/note.md": "See [other](other.md)."}}
        assert check_cross_kb_links(config, kb_file_maps) == []

class TestCrossKBEscape:
    def test_relative_link_escaping_into_other_kb(self):
        config = KBConfig(entries=[KBEntry("core", "./kb1"), KBEntry("ios", "./kb2")])
        kb_file_maps = {
            "core": {"topic/note.md": "See [other](../../../kb2/topic/note.md)."},
            "ios": {"topic/note.md": note("Note")},
        }
        issues = check_cross_kb_escape(config, kb_file_maps)
        assert len(issues) == 1
        assert issues[0].check == "cross_kb_escape"
        assert "@ios" in issues[0].message

    def test_relative_link_within_own_kb_ok(self):
        config = KBConfig(entries=[KBEntry("core", "./kb1"), KBEntry("ios", "./kb2")])
        kb_file_maps = {
            "core": {"topic/note.md": "See [other](../other/note.md).", "other/note.md": note("Other")},
            "ios": {},
        }
        assert check_cross_kb_escape(config, kb_file_maps) == []

    def test_at_links_skipped(self):
        config = KBConfig(entries=[KBEntry("core", "./kb1"), KBEntry("ios", "./kb2")])
        kb_file_maps = {"core": {"topic/note.md": "See [@ios/note.md](@ios/note.md)."}, "ios": {}}
        assert check_cross_kb_escape(config, kb_file_maps) == []

class TestValidateMultiKb:
    def test_single_valid_kb(self):
        fs = MockFileSystem({
            "kb/index.md": index("Root") + "\n- [Topic](topic/index.md)\n",
            "kb/topic/index.md": index("Topic", "Desc."),
        })
        config = KBConfig(entries=[KBEntry("core", "kb")])
        with mock.patch("validate_kb._get_git_changed_files", return_value=[]):
            result = validate_multi_kb(config, fs=fs)
        assert [e for e in result.errors if e.check != "read_error"] == []

    def test_issues_prefixed_with_kb_name(self):
        fs = MockFileSystem({"kb/index.md": "# No Frontmatter"})
        config = KBConfig(entries=[KBEntry("core", "kb")])
        with mock.patch("validate_kb._get_git_changed_files", return_value=[]):
            result = validate_multi_kb(config, fs=fs)
        fm_issues = [i for i in result.issues if i.check == "frontmatter_missing"]
        assert len(fm_issues) >= 1
        assert fm_issues[0].file.startswith("[core]")

    def test_multi_kb_aggregates_stats(self):
        fs = MockFileSystem({
            "kb1/index.md": index("Root1"),
            "kb1/topic/index.md": index("Topic"),
            "kb2/index.md": index("Root2"),
        })
        config = KBConfig(entries=[KBEntry("core", "kb1"), KBEntry("ios", "kb2")])
        with mock.patch("validate_kb._get_git_changed_files", return_value=[]):
            result = validate_multi_kb(config, fs=fs)
        assert result.stats.index_notes == 3

    def test_multi_kb_rejects_nested_paths(self):
        config = KBConfig(entries=[KBEntry("core", "./knowledge"), KBEntry("sub", "./knowledge/sub")])
        with mock.patch("validate_kb._get_git_changed_files", return_value=[]):
            result = validate_multi_kb(config)
        assert any(i.check == "nested_kb_paths" for i in result.errors)

    def test_multi_kb_cross_kb_link_validation(self):
        fs = MockFileSystem({
            "kb1/index.md": index("Root1"),
            "kb1/topic/index.md": index("Topic", "Desc") + "\nSee [@nonexistent/note.md](@nonexistent/note.md).\n",
            "kb2/index.md": index("Root2"),
        })
        config = KBConfig(entries=[KBEntry("core", "kb1"), KBEntry("ios", "kb2")])
        with mock.patch("validate_kb._get_git_changed_files", return_value=[]):
            result = validate_multi_kb(config, fs=fs)
        assert any(i.check == "unknown_cross_kb" for i in result.errors)

    def test_missing_index_detected_in_multi_kb(self):
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/no-index-topic/note.md": note("Orphan Topic", "No index."),
        })
        config = KBConfig(entries=[KBEntry("core", "kb")])
        with mock.patch("validate_kb._get_git_changed_files", return_value=[]):
            result = validate_multi_kb(config, fs=fs)
        assert any(i.check == "missing_index" for i in result.issues)

    def test_per_kb_changelog(self):
        fs = MockFileSystem({
            "kb1/index.md": index("Root1"),
            "kb2/index.md": index("Root2"),
        })
        config = KBConfig(entries=[KBEntry("core", "kb1"), KBEntry("ios", "kb2")])
        with mock.patch("validate_kb._get_git_changed_files", return_value=["kb1/topic/note.md"]):
            result = validate_multi_kb(config, fs=fs)
        changelog_issues = [i for i in result.issues if i.check == "missing_changelog"]
        assert len(changelog_issues) == 1
        assert "kb1" in changelog_issues[0].file
