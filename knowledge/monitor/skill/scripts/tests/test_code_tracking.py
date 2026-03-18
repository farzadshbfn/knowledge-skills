"""Tests for code module tracking in track_kb_access.py."""

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest
from track_kb_access import (
    extract_code_module,
    find_code_cluster,
    check_mid_session,
    main,
)
from helpers import (
    make_log_entry,
    setup_access_log,
    setup_kb_config,
    setup_topic_without_skill,
)


# ===================================================================
# extract_code_module — now returns immediate parent dir
# ===================================================================

class TestExtractCodeModule:
    def test_two_level_path(self, tmp_path):
        setup_kb_config(tmp_path)
        assert extract_code_module("src/auth/middleware.py", str(tmp_path)) == "src/auth"

    def test_deep_path_returns_immediate_parent(self, tmp_path):
        """Unlike before, nested paths track at their actual parent."""
        setup_kb_config(tmp_path)
        assert extract_code_module("src/auth/handlers/login.py", str(tmp_path)) == "src/auth/handlers"

    def test_single_level_dir(self, tmp_path):
        setup_kb_config(tmp_path)
        assert extract_code_module("lib/utils.py", str(tmp_path)) == "lib"

    def test_root_level_file_returns_none(self, tmp_path):
        setup_kb_config(tmp_path)
        assert extract_code_module("README.md", str(tmp_path)) is None

    def test_kb_file_returns_none(self, tmp_path):
        setup_kb_config(tmp_path)
        assert extract_code_module("knowledge/topic/note.md", str(tmp_path)) is None

    def test_dotfile_returns_none(self, tmp_path):
        setup_kb_config(tmp_path)
        assert extract_code_module(".claude/settings.json", str(tmp_path)) is None

    def test_gitignore_dirs_excluded(self, tmp_path):
        setup_kb_config(tmp_path)
        assert extract_code_module("node_modules/express/index.js", str(tmp_path)) is None
        assert extract_code_module(".venv/lib/site.py", str(tmp_path)) is None
        assert extract_code_module("__pycache__/module.pyc", str(tmp_path)) is None
        assert extract_code_module("build/output/main.js", str(tmp_path)) is None

    def test_relative_path_outside_project(self, tmp_path):
        setup_kb_config(tmp_path)
        assert extract_code_module("../other-project/src/main.py", str(tmp_path)) is None

    def test_tools_dir(self, tmp_path):
        setup_kb_config(tmp_path)
        assert extract_code_module("tools/kb-viewer/serve.py", str(tmp_path)) == "tools/kb-viewer"

    def test_four_level_path(self, tmp_path):
        setup_kb_config(tmp_path)
        assert extract_code_module("a/b/c/d/file.py", str(tmp_path)) == "a/b/c/d"


# ===================================================================
# find_code_cluster — hierarchical spread-scaled threshold
# ===================================================================

class TestFindCodeCluster:
    """Unit tests for the cluster detection algorithm."""

    def test_focused_reads_single_dir(self):
        """5 reads in src/auth/ → cluster = src/auth."""
        entries = [make_log_entry(f"src/auth", kind="code") for _ in range(5)]
        result = find_code_cluster(entries)
        assert result == ("src/auth", 5)

    def test_below_threshold_returns_none(self):
        """4 reads — below base threshold."""
        entries = [make_log_entry("src/auth", kind="code") for _ in range(4)]
        assert find_code_cluster(entries) is None

    def test_reads_in_dir_and_subdir_cluster_at_parent(self):
        """3 reads in src/auth/ + 2 in src/auth/handlers/ → cluster = src/auth (5 total).

        src/auth has 1 subdirectory contributing (handlers), so
        threshold = 5 + (1-1)*3 = 5. subtree reads = 5. Fires.
        """
        entries = [
            make_log_entry("src/auth", kind="code"),
            make_log_entry("src/auth", kind="code"),
            make_log_entry("src/auth", kind="code"),
            make_log_entry("src/auth/handlers", kind="code"),
            make_log_entry("src/auth/handlers", kind="code"),
        ]
        result = find_code_cluster(entries)
        assert result == ("src/auth", 5)

    def test_scattered_reads_no_cluster(self):
        """1 read each in 5 different src/ subdirs → src/ threshold = 5 + 4*3 = 17. No cluster."""
        entries = [
            make_log_entry("src/auth", kind="code"),
            make_log_entry("src/models", kind="code"),
            make_log_entry("src/api", kind="code"),
            make_log_entry("src/db", kind="code"),
            make_log_entry("src/config", kind="code"),
        ]
        assert find_code_cluster(entries) is None

    def test_two_subdirs_moderate_threshold(self):
        """Reads from 2 subdirs under src/ → threshold = 5 + 1*3 = 8."""
        entries = (
            [make_log_entry("src/auth", kind="code") for _ in range(4)]
            + [make_log_entry("src/models", kind="code") for _ in range(4)]
        )
        # src has 2 children → threshold 8, subtree = 8 → fires
        result = find_code_cluster(entries)
        assert result == ("src", 8)

    def test_two_subdirs_below_threshold(self):
        """7 reads from 2 subdirs → threshold 8, only 7 reads → no cluster."""
        entries = (
            [make_log_entry("src/auth", kind="code") for _ in range(4)]
            + [make_log_entry("src/models", kind="code") for _ in range(3)]
        )
        assert find_code_cluster(entries) is None

    def test_deepest_wins(self):
        """When both child and parent cross threshold, deepest wins."""
        entries = (
            # 5 in src/auth → fires at src/auth (threshold 5, no subdirs)
            [make_log_entry("src/auth", kind="code") for _ in range(5)]
            # 3 in src/models → not enough alone
            + [make_log_entry("src/models", kind="code") for _ in range(3)]
        )
        # src has 2 children → threshold 8, subtree = 8 → also fires
        # But src/auth (depth 2) is deeper than src (depth 1) → src/auth wins
        result = find_code_cluster(entries)
        assert result == ("src/auth", 5)

    def test_flat_dir_many_files(self):
        """5 reads in lib/ (flat dir) → cluster = lib."""
        entries = [make_log_entry("lib", kind="code") for _ in range(5)]
        result = find_code_cluster(entries)
        assert result == ("lib", 5)

    def test_deeply_nested_cluster(self):
        """5 reads in a/b/c/d/ → cluster = a/b/c/d."""
        entries = [make_log_entry("a/b/c/d", kind="code") for _ in range(5)]
        result = find_code_cluster(entries)
        assert result == ("a/b/c/d", 5)

    def test_ignores_kb_entries(self):
        """KB entries (no kind field) are excluded from code cluster analysis."""
        entries = (
            [make_log_entry("some-topic") for _ in range(10)]  # KB, no kind
            + [make_log_entry("src/auth", kind="code") for _ in range(2)]
        )
        assert find_code_cluster(entries) is None

    def test_only_counts_matching_session(self):
        """Entries from other sessions are excluded."""
        entries = (
            [make_log_entry("src/auth", sid="other-se", kind="code") for _ in range(10)]
            + [make_log_entry("src/auth", sid="sess1234", kind="code") for _ in range(3)]
        )
        assert find_code_cluster(entries, sid="sess1234") is None

    def test_empty_entries(self):
        assert find_code_cluster([]) is None

    def test_three_subdirs_threshold_11(self):
        """3 subdirs under pkg/ → threshold = 5 + 2*3 = 11."""
        entries = (
            [make_log_entry("pkg/a", kind="code") for _ in range(4)]
            + [make_log_entry("pkg/b", kind="code") for _ in range(4)]
            + [make_log_entry("pkg/c", kind="code") for _ in range(3)]
        )
        # pkg has 3 children → threshold 11, subtree = 11 → fires
        result = find_code_cluster(entries)
        assert result == ("pkg", 11)

    def test_three_subdirs_just_below(self):
        """10 reads across 3 subdirs → threshold 11, only 10 → doesn't fire."""
        entries = (
            [make_log_entry("pkg/a", kind="code") for _ in range(4)]
            + [make_log_entry("pkg/b", kind="code") for _ in range(3)]
            + [make_log_entry("pkg/c", kind="code") for _ in range(3)]
        )
        assert find_code_cluster(entries) is None


# ===================================================================
# code reads logged with kind=code
# ===================================================================

class TestCodeLogging:
    def _run_main(self, monkeypatch, data: dict) -> int:
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(data)))
        return main()

    def test_code_read_creates_log_entry(self, tmp_path, monkeypatch):
        setup_kb_config(tmp_path)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)
        cwd = str(tmp_path)
        data = {
            "session_id": "test-session-id-12345",
            "cwd": cwd,
            "tool_input": {"file_path": f"{cwd}/src/auth/middleware.py"},
        }
        result = self._run_main(monkeypatch, data)
        assert result == 0

        log_file = tmp_path / ".claude" / "knowledge-base" / "access-log.jsonl"
        assert log_file.exists()
        entry = json.loads(log_file.read_text().strip())
        assert entry["topic"] == "src/auth"
        assert entry["kind"] == "code"

    def test_deep_path_logged_at_immediate_parent(self, tmp_path, monkeypatch):
        setup_kb_config(tmp_path)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)
        cwd = str(tmp_path)
        data = {
            "session_id": "test-session-id-12345",
            "cwd": cwd,
            "tool_input": {"file_path": f"{cwd}/src/auth/handlers/login.py"},
        }
        self._run_main(monkeypatch, data)

        log_file = tmp_path / ".claude" / "knowledge-base" / "access-log.jsonl"
        entry = json.loads(log_file.read_text().strip())
        assert entry["topic"] == "src/auth/handlers"

    def test_kb_read_has_no_kind_field(self, tmp_path, monkeypatch):
        setup_kb_config(tmp_path)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)
        cwd = str(tmp_path)
        data = {
            "session_id": "test-session",
            "cwd": cwd,
            "tool_input": {"file_path": f"{cwd}/knowledge/topic/note.md"},
        }
        self._run_main(monkeypatch, data)

        log_file = tmp_path / ".claude" / "knowledge-base" / "access-log.jsonl"
        entry = json.loads(log_file.read_text().strip())
        assert "kind" not in entry

    def test_dotfile_not_logged(self, tmp_path, monkeypatch):
        setup_kb_config(tmp_path)
        cwd = str(tmp_path)
        data = {
            "session_id": "test-session",
            "cwd": cwd,
            "tool_input": {"file_path": f"{cwd}/.claude/settings.json"},
        }
        self._run_main(monkeypatch, data)
        log_file = tmp_path / ".claude" / "knowledge-base" / "access-log.jsonl"
        assert not log_file.exists()

    def test_root_file_not_logged(self, tmp_path, monkeypatch):
        setup_kb_config(tmp_path)
        cwd = str(tmp_path)
        data = {
            "session_id": "test-session",
            "cwd": cwd,
            "tool_input": {"file_path": f"{cwd}/README.md"},
        }
        self._run_main(monkeypatch, data)
        log_file = tmp_path / ".claude" / "knowledge-base" / "access-log.jsonl"
        assert not log_file.exists()


# ===================================================================
# code mid-session nudge (via check_mid_session → find_code_cluster)
# ===================================================================

class TestCodeMidSession:
    def test_below_threshold_no_output(self, tmp_path, capsys, monkeypatch):
        entries = [make_log_entry("src/auth", sid="sess1234", kind="code") for _ in range(4)]
        log_file = setup_access_log(tmp_path, entries)
        setup_kb_config(tmp_path)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)

        check_mid_session(str(log_file), "sess1234", "src/auth", str(tmp_path), kind="code")
        assert capsys.readouterr().out == ""

    def test_at_threshold_emits_nudge(self, tmp_path, capsys, monkeypatch):
        entries = [make_log_entry("src/auth", sid="sess1234", kind="code") for _ in range(5)]
        log_file = setup_access_log(tmp_path, entries)
        setup_kb_config(tmp_path)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)

        check_mid_session(str(log_file), "sess1234", "src/auth", str(tmp_path), kind="code")
        out = capsys.readouterr().out
        msg = json.loads(out)
        assert "systemMessage" in msg
        assert "src/auth" in msg["systemMessage"]
        assert "skill" in msg["systemMessage"].lower()

    def test_code_nudge_does_not_reference_monitoring_convert(self, tmp_path, capsys, monkeypatch):
        entries = [make_log_entry("src/auth", sid="sess1234", kind="code") for _ in range(5)]
        log_file = setup_access_log(tmp_path, entries)
        setup_kb_config(tmp_path)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)

        check_mid_session(str(log_file), "sess1234", "src/auth", str(tmp_path), kind="code")
        out = capsys.readouterr().out
        msg = json.loads(out)
        assert "--convert" not in msg["systemMessage"]

    def test_marker_prevents_duplicate_code_nudge(self, tmp_path, capsys, monkeypatch):
        entries = [make_log_entry("src/auth", sid="sess1234", kind="code") for _ in range(5)]
        log_file = setup_access_log(tmp_path, entries)
        setup_kb_config(tmp_path)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)

        check_mid_session(str(log_file), "sess1234", "src/auth", str(tmp_path), kind="code")
        first_out = capsys.readouterr().out
        assert "systemMessage" in first_out

        check_mid_session(str(log_file), "sess1234", "src/auth", str(tmp_path), kind="code")
        assert capsys.readouterr().out == ""

    def test_kb_threshold_still_3(self, tmp_path, capsys, monkeypatch):
        """KB topics should still trigger at 3, not 5."""
        entries = [make_log_entry("my-topic", sid="sess1234") for _ in range(3)]
        log_file = setup_access_log(tmp_path, entries)
        setup_kb_config(tmp_path)
        setup_topic_without_skill(tmp_path, "my-topic")
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)

        check_mid_session(str(log_file), "sess1234", "my-topic", str(tmp_path))
        out = capsys.readouterr().out
        assert "systemMessage" in out

    def test_scattered_code_reads_no_nudge(self, tmp_path, capsys, monkeypatch):
        """5 reads across 5 different src/ subdirs → no nudge (spread too wide)."""
        entries = [
            make_log_entry("src/auth", sid="sess1234", kind="code"),
            make_log_entry("src/models", sid="sess1234", kind="code"),
            make_log_entry("src/api", sid="sess1234", kind="code"),
            make_log_entry("src/db", sid="sess1234", kind="code"),
            make_log_entry("src/config", sid="sess1234", kind="code"),
        ]
        log_file = setup_access_log(tmp_path, entries)
        setup_kb_config(tmp_path)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)

        # Trigger check from any of these
        check_mid_session(str(log_file), "sess1234", "src/config", str(tmp_path), kind="code")
        assert capsys.readouterr().out == ""
