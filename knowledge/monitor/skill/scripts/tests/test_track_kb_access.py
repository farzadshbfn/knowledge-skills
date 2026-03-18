"""Tests for track_kb_access.py — async PostToolUse hook for KB read tracking."""

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest
from track_kb_access import (
    extract_topic,
    is_gated,
    main,
    topic_has_skill,
    trim_old_entries,
    check_mid_session,
)
from helpers import (
    MEMORY_EMPTY,
    MEMORY_WITH_GATES,
    make_log_entry,
    setup_access_log,
    setup_kb_config,
    setup_memory_dir,
    setup_topic_with_skill,
    setup_topic_without_skill,
)


# ===================================================================
# extract_topic
# ===================================================================

class TestExtractTopic:
    def test_valid_kb_path(self, tmp_path):
        setup_kb_config(tmp_path)
        result = extract_topic("knowledge/claude-hooks/hooks-overview.md", str(tmp_path))
        assert result == "claude-hooks"

    def test_nested_path_extracts_top_topic(self, tmp_path):
        setup_kb_config(tmp_path)
        result = extract_topic(
            "knowledge/claude-hooks/skill/reference/workflow.md", str(tmp_path)
        )
        assert result == "claude-hooks"

    def test_non_kb_path_returns_none(self, tmp_path):
        setup_kb_config(tmp_path)
        assert extract_topic(".claude/settings.json", str(tmp_path)) is None

    def test_changelog_not_tracked(self, tmp_path):
        setup_kb_config(tmp_path)
        assert extract_topic("knowledge/CHANGELOG.md", str(tmp_path)) is None

    def test_root_index_not_tracked(self, tmp_path):
        setup_kb_config(tmp_path)
        # Root-level files (single segment after KB root) are not tracked
        result = extract_topic("knowledge/index.md", str(tmp_path))
        assert result is None

    def test_missing_config_falls_back_to_knowledge(self, tmp_path):
        # No config file created
        result = extract_topic("knowledge/my-topic/note.md", str(tmp_path))
        assert result == "my-topic"

    def test_custom_kb_root(self, tmp_path):
        setup_kb_config(tmp_path, [{"name": "ios", "path": "./ios/knowledge"}])
        result = extract_topic("ios/knowledge/swift/overview.md", str(tmp_path))
        assert result == "swift"

    def test_multiple_kb_roots(self, tmp_path):
        setup_kb_config(tmp_path, [
            {"name": "core", "path": "./knowledge"},
            {"name": "ios", "path": "./ios/knowledge"},
        ])
        assert extract_topic("knowledge/hooks/note.md", str(tmp_path)) == "hooks"
        assert extract_topic("ios/knowledge/swift/note.md", str(tmp_path)) == "swift"

    def test_empty_path_returns_none(self, tmp_path):
        setup_kb_config(tmp_path)
        assert extract_topic("", str(tmp_path)) is None

    def test_path_outside_kb(self, tmp_path):
        setup_kb_config(tmp_path)
        assert extract_topic("src/other/file.md", str(tmp_path)) is None


# ===================================================================
# trim_old_entries
# ===================================================================

class TestTrimOldEntries:
    def test_skips_when_under_threshold(self, tmp_path):
        """Files under 1000 lines are not trimmed."""
        log_file = setup_access_log(tmp_path, [
            make_log_entry("topic-a", ts="2020-01-01T00:00:00"),  # very old
            make_log_entry("topic-b", ts="2026-03-14T00:00:00"),  # recent
        ])
        trim_old_entries(str(log_file))
        # Both entries kept because file is under 1000 lines
        lines = [l for l in log_file.read_text().strip().split("\n") if l]
        assert len(lines) == 2

    def test_removes_old_entries_when_over_threshold(self, tmp_path):
        """Files over 1000 lines get old entries trimmed."""
        entries = []
        # 500 old entries
        for i in range(500):
            entries.append(make_log_entry("old", sid=f"old{i:05d}", ts="2020-01-01T00:00:00"))
        # 600 recent entries
        for i in range(600):
            entries.append(make_log_entry("new", sid=f"new{i:05d}", ts="2026-03-14T00:00:00"))
        log_file = setup_access_log(tmp_path, entries)
        assert len(log_file.read_text().strip().split("\n")) == 1100

        trim_old_entries(str(log_file))
        remaining = [l for l in log_file.read_text().strip().split("\n") if l]
        assert len(remaining) == 600
        # All remaining are "new" topic
        for line in remaining:
            assert json.loads(line)["topic"] == "new"

    def test_handles_missing_file(self, tmp_path):
        """Does not crash on missing log file."""
        trim_old_entries(str(tmp_path / "nonexistent.jsonl"))

    def test_handles_malformed_entries(self, tmp_path):
        """Malformed JSON lines are dropped during trim."""
        log_dir = tmp_path / ".claude" / "knowledge-base"
        log_dir.mkdir(parents=True)
        log_file = log_dir / "access-log.jsonl"
        lines = []
        for i in range(600):
            lines.append(json.dumps(make_log_entry("good", ts="2026-03-14T00:00:00")))
        # Add malformed entries to push over 1000
        for i in range(500):
            lines.append("not valid json {{{")
        log_file.write_text("\n".join(lines) + "\n")

        trim_old_entries(str(log_file))
        remaining = [l for l in log_file.read_text().strip().split("\n") if l]
        # Only valid recent entries kept, malformed dropped
        assert len(remaining) == 600


# ===================================================================
# topic_has_skill
# ===================================================================

class TestTopicHasSkill:
    def test_topic_with_skill(self, tmp_path):
        setup_kb_config(tmp_path)
        setup_topic_with_skill(tmp_path, "claude-hooks")
        assert topic_has_skill("claude-hooks", str(tmp_path)) is True

    def test_topic_without_skill(self, tmp_path):
        setup_kb_config(tmp_path)
        setup_topic_without_skill(tmp_path, "plain-topic")
        assert topic_has_skill("plain-topic", str(tmp_path)) is False

    def test_nonexistent_topic(self, tmp_path):
        setup_kb_config(tmp_path)
        assert topic_has_skill("no-such-topic", str(tmp_path)) is False

    def test_fallback_without_config(self, tmp_path):
        """Falls back to knowledge/ when config is missing."""
        setup_topic_with_skill(tmp_path, "fallback-topic")
        assert topic_has_skill("fallback-topic", str(tmp_path)) is True

    def test_custom_kb_root(self, tmp_path):
        setup_kb_config(tmp_path, [{"name": "ios", "path": "./ios/knowledge"}])
        skill_dir = tmp_path / "ios" / "knowledge" / "swift" / "skill"
        skill_dir.mkdir(parents=True)
        assert topic_has_skill("swift", str(tmp_path)) is True


# ===================================================================
# is_gated
# ===================================================================

class TestIsGated:
    def test_excluded_topic(self, tmp_path, monkeypatch):
        mem_dir = setup_memory_dir(tmp_path, MEMORY_WITH_GATES)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: str(mem_dir))
        assert is_gated("excluded-topic", str(tmp_path)) is True

    def test_cooldown_topic(self, tmp_path, monkeypatch):
        mem_dir = setup_memory_dir(tmp_path, MEMORY_WITH_GATES)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: str(mem_dir))
        assert is_gated("cooldown-topic", str(tmp_path)) is True

    def test_condition_topic(self, tmp_path, monkeypatch):
        mem_dir = setup_memory_dir(tmp_path, MEMORY_WITH_GATES)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: str(mem_dir))
        assert is_gated("condition-topic", str(tmp_path)) is True

    def test_ungated_topic(self, tmp_path, monkeypatch):
        mem_dir = setup_memory_dir(tmp_path, MEMORY_WITH_GATES)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: str(mem_dir))
        assert is_gated("some-other-topic", str(tmp_path)) is False

    def test_missing_memory_file(self, tmp_path, monkeypatch):
        mem_dir = setup_memory_dir(tmp_path)  # no content file
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: str(mem_dir))
        assert is_gated("any-topic", str(tmp_path)) is False

    def test_no_memory_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)
        assert is_gated("any-topic", str(tmp_path)) is False

    def test_empty_gates_table(self, tmp_path, monkeypatch):
        mem_dir = setup_memory_dir(tmp_path, MEMORY_EMPTY)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: str(mem_dir))
        assert is_gated("any-topic", str(tmp_path)) is False


# ===================================================================
# check_mid_session
# ===================================================================

class TestCheckMidSession:
    def test_below_threshold_no_output(self, tmp_path, capsys):
        """Under 3 reads — no systemMessage emitted."""
        entries = [make_log_entry("my-topic", sid="sess1234") for _ in range(2)]
        log_file = setup_access_log(tmp_path, entries)
        setup_kb_config(tmp_path)
        setup_topic_without_skill(tmp_path, "my-topic")

        check_mid_session(str(log_file), "sess1234", "my-topic", str(tmp_path))
        assert capsys.readouterr().out == ""

    def test_at_threshold_emits_system_message(self, tmp_path, capsys, monkeypatch):
        """At 3+ reads of non-skill topic — emits systemMessage."""
        entries = [make_log_entry("my-topic", sid="sess1234") for _ in range(3)]
        log_file = setup_access_log(tmp_path, entries)
        setup_kb_config(tmp_path)
        setup_topic_without_skill(tmp_path, "my-topic")
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)

        check_mid_session(str(log_file), "sess1234", "my-topic", str(tmp_path))
        out = capsys.readouterr().out
        msg = json.loads(out)
        assert "systemMessage" in msg
        assert "my-topic" in msg["systemMessage"]
        assert "3 times" in msg["systemMessage"]

    def test_topic_with_skill_no_output(self, tmp_path, capsys, monkeypatch):
        """Topics that already have a skill/ get no recommendation."""
        entries = [make_log_entry("skilled-topic", sid="sess1234") for _ in range(10)]
        log_file = setup_access_log(tmp_path, entries)
        setup_kb_config(tmp_path)
        setup_topic_with_skill(tmp_path, "skilled-topic")
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)

        check_mid_session(str(log_file), "sess1234", "skilled-topic", str(tmp_path))
        assert capsys.readouterr().out == ""

    def test_gated_topic_no_output(self, tmp_path, capsys, monkeypatch):
        """Gated topics are suppressed."""
        entries = [make_log_entry("excluded-topic", sid="sess1234") for _ in range(10)]
        log_file = setup_access_log(tmp_path, entries)
        setup_kb_config(tmp_path)
        setup_topic_without_skill(tmp_path, "excluded-topic")
        mem_dir = setup_memory_dir(tmp_path, MEMORY_WITH_GATES)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: str(mem_dir))

        check_mid_session(str(log_file), "sess1234", "excluded-topic", str(tmp_path))
        assert capsys.readouterr().out == ""

    def test_marker_prevents_duplicate(self, tmp_path, capsys, monkeypatch):
        """Once emitted for a session+topic, don't emit again."""
        entries = [make_log_entry("my-topic", sid="sess1234") for _ in range(3)]
        log_file = setup_access_log(tmp_path, entries)
        setup_kb_config(tmp_path)
        setup_topic_without_skill(tmp_path, "my-topic")
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)

        # First call emits
        check_mid_session(str(log_file), "sess1234", "my-topic", str(tmp_path))
        first_out = capsys.readouterr().out
        assert "systemMessage" in first_out

        # Second call is suppressed by marker
        check_mid_session(str(log_file), "sess1234", "my-topic", str(tmp_path))
        assert capsys.readouterr().out == ""

    def test_empty_session_id_no_output(self, tmp_path, capsys):
        """Empty session ID — skip mid-session check."""
        entries = [make_log_entry("my-topic", sid="") for _ in range(10)]
        log_file = setup_access_log(tmp_path, entries)

        check_mid_session(str(log_file), "", "my-topic", str(tmp_path))
        assert capsys.readouterr().out == ""

    def test_different_sessions_not_mixed(self, tmp_path, capsys, monkeypatch):
        """Reads from different sessions don't aggregate."""
        entries = [
            make_log_entry("my-topic", sid="sess1111"),
            make_log_entry("my-topic", sid="sess1111"),
            make_log_entry("my-topic", sid="sess2222"),
            make_log_entry("my-topic", sid="sess2222"),
            make_log_entry("my-topic", sid="sess2222"),
        ]
        log_file = setup_access_log(tmp_path, entries)
        setup_kb_config(tmp_path)
        setup_topic_without_skill(tmp_path, "my-topic")
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)

        # sess1111 only has 2 reads — below threshold
        check_mid_session(str(log_file), "sess1111", "my-topic", str(tmp_path))
        assert capsys.readouterr().out == ""


# ===================================================================
# main (integration)
# ===================================================================

class TestMain:
    def _run_main(self, monkeypatch, data: dict) -> int:
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(data)))
        return main()

    def test_logs_kb_read(self, tmp_path, monkeypatch):
        """A Read of a KB file creates a log entry."""
        setup_kb_config(tmp_path)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)
        cwd = str(tmp_path)
        data = {
            "session_id": "test-session-id-12345",
            "cwd": cwd,
            "tool_input": {
                "file_path": f"{cwd}/knowledge/claude-hooks/overview.md",
            },
        }
        result = self._run_main(monkeypatch, data)
        assert result == 0

        log_file = tmp_path / ".claude" / "knowledge-base" / "access-log.jsonl"
        assert log_file.exists()
        entry = json.loads(log_file.read_text().strip())
        assert entry["topic"] == "claude-hooks"
        assert entry["sid"] == "test-ses"  # truncated to 8 chars

    def test_non_kb_file_no_logging(self, tmp_path, monkeypatch):
        """A Read of a non-KB file produces no log entry."""
        setup_kb_config(tmp_path)
        cwd = str(tmp_path)
        data = {
            "session_id": "test-session",
            "cwd": cwd,
            "tool_input": {"file_path": f"{cwd}/.claude/settings.json"},
        }
        result = self._run_main(monkeypatch, data)
        assert result == 0
        log_file = tmp_path / ".claude" / "knowledge-base" / "access-log.jsonl"
        assert not log_file.exists()

    def test_missing_file_path_no_crash(self, tmp_path, monkeypatch):
        data = {"session_id": "test", "cwd": str(tmp_path), "tool_input": {}}
        assert self._run_main(monkeypatch, data) == 0

    def test_malformed_json_stdin_no_crash(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
        assert main() == 0

    def test_empty_stdin_no_crash(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert main() == 0

    def test_multiple_reads_accumulate(self, tmp_path, monkeypatch):
        """Multiple KB reads append to the same log file."""
        setup_kb_config(tmp_path)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)
        cwd = str(tmp_path)

        for i in range(3):
            data = {
                "session_id": "sess-abc",
                "cwd": cwd,
                "tool_input": {
                    "file_path": f"{cwd}/knowledge/topic-{i}/note.md",
                },
            }
            monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(data)))
            main()

        log_file = tmp_path / ".claude" / "knowledge-base" / "access-log.jsonl"
        lines = [l for l in log_file.read_text().strip().split("\n") if l]
        assert len(lines) == 3
        topics = {json.loads(l)["topic"] for l in lines}
        assert topics == {"topic-0", "topic-1", "topic-2"}

    def test_absolute_path_resolved_to_relative(self, tmp_path, monkeypatch):
        """Absolute file paths are resolved relative to cwd."""
        setup_kb_config(tmp_path)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)
        cwd = str(tmp_path)
        data = {
            "session_id": "sess123",
            "cwd": cwd,
            "tool_input": {
                "file_path": f"{cwd}/knowledge/my-topic/deep/note.md",
            },
        }
        result = self._run_main(monkeypatch, data)
        assert result == 0

        log_file = tmp_path / ".claude" / "knowledge-base" / "access-log.jsonl"
        entry = json.loads(log_file.read_text().strip())
        assert entry["topic"] == "my-topic"
        assert entry["path"] == "knowledge/my-topic/deep/note.md"
