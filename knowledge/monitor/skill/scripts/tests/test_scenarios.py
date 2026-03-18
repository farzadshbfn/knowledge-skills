"""End-to-end scenarios showing how access tracking works in a real session.

Each test simulates a developer session: multiple Read tool calls arrive,
the hook logs them, and at the right moment a systemMessage nudge fires.
"""

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest
from track_kb_access import main
from helpers import setup_kb_config, setup_topic_without_skill, setup_topic_with_skill


def simulate_read(monkeypatch, cwd: str, file_path: str, session_id: str = "sess-abc-123") -> int:
    """Simulate a single PostToolUse Read event."""
    data = {
        "session_id": session_id,
        "cwd": cwd,
        "tool_input": {"file_path": file_path},
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(data)))
    return main()


def get_log_entries(tmp_path: Path) -> list[dict]:
    log_file = tmp_path / ".claude" / "knowledge-base" / "access-log.jsonl"
    if not log_file.exists():
        return []
    return [json.loads(l) for l in log_file.read_text().strip().split("\n") if l.strip()]


class TestScenarioFocusedCodeCluster:
    """Developer debugging an auth module — reads several files in the same area."""

    def test_auth_module_nudge_after_5_focused_reads(self, tmp_path, monkeypatch, capsys):
        """5 reads clustering in src/auth/ (including subdirs) → nudge about src/auth."""
        setup_kb_config(tmp_path)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)
        cwd = str(tmp_path)

        reads = [
            # Developer investigating an auth bug
            (f"{cwd}/src/auth/middleware.py",      False, "src/auth read 1"),
            (f"{cwd}/src/auth/tokens.py",          False, "src/auth read 2"),
            (f"{cwd}/src/models/user.py",          False, "src/models read 1 (different module)"),
            (f"{cwd}/src/auth/handlers/login.py",  False, "src/auth/handlers read 1 (child dir, bubbles up)"),
            (f"{cwd}/src/auth/handlers/oauth.py",  False, "src/auth/handlers read 2"),
            (f"{cwd}/src/auth/config.py",          True,  "src/auth total=5 (3 direct + 2 handlers) → NUDGE"),
        ]

        for path, expect_nudge, reason in reads:
            capsys.readouterr()
            simulate_read(monkeypatch, cwd, path)
            out = capsys.readouterr().out

            if expect_nudge:
                msg = json.loads(out)
                assert "systemMessage" in msg, f"Expected nudge: {reason}"
                assert "src/auth" in msg["systemMessage"]
                assert "skill" in msg["systemMessage"].lower()
            else:
                assert out == "", f"No nudge expected: {reason}, got: {out}"

    def test_no_nudge_at_4_reads(self, tmp_path, monkeypatch, capsys):
        """4 reads of the same code area — still below threshold."""
        setup_kb_config(tmp_path)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)
        cwd = str(tmp_path)

        for path in [
            f"{cwd}/src/auth/middleware.py",
            f"{cwd}/src/auth/tokens.py",
            f"{cwd}/src/auth/handlers/login.py",
            f"{cwd}/src/auth/config.py",
        ]:
            capsys.readouterr()
            simulate_read(monkeypatch, cwd, path)
            assert capsys.readouterr().out == ""


class TestScenarioScatteredReads:
    """Reads spread across many subdirs of src/ — should NOT trigger."""

    def test_5_reads_across_5_subdirs_no_nudge(self, tmp_path, monkeypatch, capsys):
        """src/ has 5 unique children → threshold = 5 + 4*3 = 17. Only 5 reads. No nudge.

        This is the key scenario: in a project where everything is under src/,
        casual browsing should never trigger a nudge for src/ itself.
        """
        setup_kb_config(tmp_path)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)
        cwd = str(tmp_path)

        for path in [
            f"{cwd}/src/auth/middleware.py",
            f"{cwd}/src/models/user.py",
            f"{cwd}/src/api/routes.py",
            f"{cwd}/src/db/connection.py",
            f"{cwd}/src/config/settings.py",
        ]:
            capsys.readouterr()
            simulate_read(monkeypatch, cwd, path)
            assert capsys.readouterr().out == "", f"No nudge for scattered reads: {path}"

    def test_10_reads_across_5_subdirs_still_no_nudge(self, tmp_path, monkeypatch, capsys):
        """Even 10 reads across 5 subdirs doesn't hit threshold 17."""
        setup_kb_config(tmp_path)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)
        cwd = str(tmp_path)

        for path in [
            f"{cwd}/src/auth/a.py", f"{cwd}/src/auth/b.py",
            f"{cwd}/src/models/a.py", f"{cwd}/src/models/b.py",
            f"{cwd}/src/api/a.py", f"{cwd}/src/api/b.py",
            f"{cwd}/src/db/a.py", f"{cwd}/src/db/b.py",
            f"{cwd}/src/config/a.py", f"{cwd}/src/config/b.py",
        ]:
            capsys.readouterr()
            simulate_read(monkeypatch, cwd, path)
            assert capsys.readouterr().out == ""


class TestScenarioTwoSubdirsFocused:
    """Reads concentrated in 2 subdirs of src/ — moderate threshold."""

    def test_8_reads_across_2_subdirs_nudges_at_src(self, tmp_path, monkeypatch, capsys):
        """2 children under src/ → threshold = 5 + 1*3 = 8. At 8 reads, src fires.

        But if one child already has 5, it fires first (deepest wins).
        """
        setup_kb_config(tmp_path)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)
        cwd = str(tmp_path)

        nudge_fired = False
        nudge_target = None
        for path in [
            f"{cwd}/src/auth/a.py",      # auth=1
            f"{cwd}/src/auth/b.py",       # auth=2
            f"{cwd}/src/models/a.py",     # models=1
            f"{cwd}/src/auth/c.py",       # auth=3
            f"{cwd}/src/models/b.py",     # models=2
            f"{cwd}/src/auth/d.py",       # auth=4
            f"{cwd}/src/models/c.py",     # models=3
            f"{cwd}/src/auth/e.py",       # auth=5 → src/auth fires (deepest at threshold)
        ]:
            capsys.readouterr()
            simulate_read(monkeypatch, cwd, path)
            out = capsys.readouterr().out
            if out and not nudge_fired:
                nudge_fired = True
                msg = json.loads(out)
                nudge_target = msg["systemMessage"]

        assert nudge_fired
        # Deepest cluster wins: src/auth has 5 reads (threshold 5, no subdirs)
        assert "src/auth" in nudge_target


class TestScenarioKBTopic:
    """KB topic notes — triggers at 3 reads (unchanged)."""

    def test_kb_topic_nudge_after_3_reads(self, tmp_path, monkeypatch, capsys):
        setup_kb_config(tmp_path)
        setup_topic_without_skill(tmp_path, "claude-hooks")
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)
        cwd = str(tmp_path)

        reads = [
            f"{cwd}/knowledge/claude-hooks/index.md",
            f"{cwd}/knowledge/claude-hooks/hook-types.md",
            f"{cwd}/knowledge/claude-hooks/examples.md",
        ]

        for i, path in enumerate(reads):
            capsys.readouterr()
            simulate_read(monkeypatch, cwd, path)
            out = capsys.readouterr().out

            if i < 2:
                assert out == "", f"Read {i+1} should not produce output"
            else:
                msg = json.loads(out)
                assert "systemMessage" in msg
                assert "claude-hooks/" in msg["systemMessage"]
                assert "3 times" in msg["systemMessage"]
                assert "/kb-monitor --convert" in msg["systemMessage"]

    def test_kb_topic_with_skill_never_nudges(self, tmp_path, monkeypatch, capsys):
        setup_kb_config(tmp_path)
        setup_topic_with_skill(tmp_path, "kb-management")
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)
        cwd = str(tmp_path)

        for _ in range(10):
            capsys.readouterr()
            simulate_read(monkeypatch, cwd,
                          f"{cwd}/knowledge/kb-management/index.md")
            assert capsys.readouterr().out == ""


class TestScenarioMixedSession:
    """Interleaved KB and code reads — independent tracking."""

    def test_mixed_kb_and_code_independent_thresholds(self, tmp_path, monkeypatch, capsys):
        setup_kb_config(tmp_path)
        setup_topic_without_skill(tmp_path, "swift-concurrency")
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)
        cwd = str(tmp_path)

        sequence = [
            (f"{cwd}/knowledge/swift-concurrency/actors.md", False, "KB read 1"),
            (f"{cwd}/Sources/Networking/client.swift",                False, "code read 1"),
            (f"{cwd}/knowledge/swift-concurrency/sendable.md", False, "KB read 2"),
            (f"{cwd}/Sources/Networking/request.swift",               False, "code read 2"),
            (f"{cwd}/knowledge/swift-concurrency/tasks.md",  True,  "KB read 3 → nudge"),
            (f"{cwd}/Sources/Networking/response.swift",              False, "code read 3"),
            (f"{cwd}/Sources/Networking/auth.swift",                  False, "code read 4"),
            (f"{cwd}/Sources/Networking/cache.swift",                 True,  "code read 5 → nudge"),
        ]

        for path, expect_nudge, reason in sequence:
            capsys.readouterr()
            simulate_read(monkeypatch, cwd, path)
            out = capsys.readouterr().out

            if expect_nudge:
                assert out != "", f"Expected nudge at: {reason}"
                msg = json.loads(out)
                assert "systemMessage" in msg
            else:
                assert out == "", f"Unexpected nudge at: {reason}"


class TestScenarioIgnoredPaths:
    """Files that should never be tracked."""

    def test_ignored_paths_produce_no_entries(self, tmp_path, monkeypatch, capsys):
        setup_kb_config(tmp_path)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)
        cwd = str(tmp_path)

        for path in [
            f"{cwd}/README.md",
            f"{cwd}/.claude/settings.json",
            f"{cwd}/.git/config",
            f"{cwd}/node_modules/express/index.js",
            f"{cwd}/__pycache__/module.cpython-312.pyc",
            f"{cwd}/build/output/main.js",
            f"{cwd}/DerivedData/Build/Products/app",
            f"{cwd}/.venv/lib/python3.12/site.py",
        ]:
            simulate_read(monkeypatch, cwd, path)

        assert get_log_entries(tmp_path) == []


class TestScenarioNudgeOnlyOnce:
    """After the nudge fires, continued reads don't repeat it."""

    def test_nudge_fires_once_then_silent(self, tmp_path, monkeypatch, capsys):
        setup_kb_config(tmp_path)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)
        cwd = str(tmp_path)

        nudge_count = 0
        for i in range(10):
            capsys.readouterr()
            simulate_read(monkeypatch, cwd, f"{cwd}/lib/payments/charge_{i}.py")
            out = capsys.readouterr().out
            if out:
                nudge_count += 1
                msg = json.loads(out)
                assert "lib/payments" in msg["systemMessage"]

        assert nudge_count == 1


class TestScenarioDeepNesting:
    """Reads deep in the tree cluster at the right level."""

    def test_deep_reads_cluster_at_immediate_parent(self, tmp_path, monkeypatch, capsys):
        """All reads in a/b/c/d/ → nudge about a/b/c/d, not a/ or a/b/."""
        setup_kb_config(tmp_path)
        monkeypatch.setattr("track_kb_access._find_memory_dir", lambda cwd: None)
        cwd = str(tmp_path)

        nudge_msg = None
        for i in range(5):
            capsys.readouterr()
            simulate_read(monkeypatch, cwd, f"{cwd}/app/features/auth/views/screen_{i}.swift")
            out = capsys.readouterr().out
            if out:
                nudge_msg = json.loads(out)["systemMessage"]

        assert nudge_msg is not None
        assert "app/features/auth/views" in nudge_msg
