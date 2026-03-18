"""Tests for --hook mode — stdin parsing, file-in-KB check, exit codes, multi-KB."""

import io
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_kb import KBConfig, KBEntry, _check_file_in_kb, _read_hook_input, main
from helpers import note, index


class TestCheckFileInKB:
    def test_file_inside_single_kb(self, tmp_path):
        kb = tmp_path / "knowledge"
        kb.mkdir()
        config = KBConfig(entries=[KBEntry("core", str(kb))])
        assert _check_file_in_kb(config, str(kb / "topic/note.md"))

    def test_file_outside_single_kb(self, tmp_path):
        kb = tmp_path / "knowledge"
        kb.mkdir()
        config = KBConfig(entries=[KBEntry("core", str(kb))])
        assert not _check_file_in_kb(config, str(tmp_path / "other/file.md"))

    def test_file_inside_second_kb(self, tmp_path):
        kb1 = tmp_path / "kb1"
        kb2 = tmp_path / "kb2"
        kb1.mkdir()
        kb2.mkdir()
        config = KBConfig(entries=[KBEntry("core", str(kb1)), KBEntry("ios", str(kb2))])
        assert _check_file_in_kb(config, str(kb2 / "note.md"))

    def test_file_outside_all_kbs(self, tmp_path):
        kb1 = tmp_path / "kb1"
        kb2 = tmp_path / "kb2"
        kb1.mkdir()
        kb2.mkdir()
        config = KBConfig(entries=[KBEntry("core", str(kb1)), KBEntry("ios", str(kb2))])
        assert not _check_file_in_kb(config, str(tmp_path / "unrelated/file.md"))

    def test_file_at_kb_root_itself(self, tmp_path):
        kb = tmp_path / "knowledge"
        kb.mkdir()
        config = KBConfig(entries=[KBEntry("core", str(kb))])
        assert _check_file_in_kb(config, str(kb / "CHANGELOG.md"))

    def test_relative_kb_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        kb = tmp_path / "knowledge"
        kb.mkdir()
        config = KBConfig(entries=[KBEntry("core", "./knowledge")])
        assert _check_file_in_kb(config, str(kb / "note.md"))

    def test_similar_prefix_no_false_match(self, tmp_path):
        kb = tmp_path / "knowledge"
        kb.mkdir()
        extra = tmp_path / "knowledge-extra"
        extra.mkdir()
        config = KBConfig(entries=[KBEntry("core", str(kb))])
        assert not _check_file_in_kb(config, str(extra / "note.md"))


class TestReadHookInput:
    def test_valid_json(self):
        import select as select_mod
        hook_json = '{"tool_input": {"file_path": "/tmp/test.md"}, "cwd": "/tmp"}'
        with mock.patch.object(select_mod, "select", return_value=([True], [], [])):
            with mock.patch("validate_kb.sys.stdin", io.StringIO(hook_json)):
                result = _read_hook_input()
        assert result == {"tool_input": {"file_path": "/tmp/test.md"}, "cwd": "/tmp"}

    def test_no_stdin(self):
        import select as select_mod
        with mock.patch.object(select_mod, "select", return_value=([], [], [])):
            assert _read_hook_input() is None

    def test_invalid_json(self):
        import select as select_mod
        with mock.patch.object(select_mod, "select", return_value=([True], [], [])):
            with mock.patch("validate_kb.sys.stdin", io.StringIO("not json")):
                assert _read_hook_input() is None


class TestHookMode:
    def _setup_kb(self, tmp_path):
        kb = tmp_path / "knowledge"
        topics = kb / "topic"
        topics.mkdir(parents=True)
        (topics / "index.md").write_text(index("Topic"))
        (topics / "note.md").write_text(note("Note"))

        config_dir = tmp_path / ".claude" / "knowledge-base"
        config_dir.mkdir(parents=True)
        (config_dir / "config.json").write_text(
            '{"kb_roots": [{"name": "core", "path": "./knowledge"}]}'
        )
        return kb

    def test_hook_skips_file_outside_kb(self, tmp_path, monkeypatch, capsys):
        self._setup_kb(tmp_path)
        monkeypatch.chdir(tmp_path)

        hook_json = {"tool_input": {"file_path": str(tmp_path / "other" / "file.md")}}
        with mock.patch("validate_kb._read_hook_input", return_value=hook_json):
            with mock.patch("validate_kb._get_git_changed_files", return_value=[]):
                rc = main(["--hook", "--quiet"])
        assert rc == 0
        assert capsys.readouterr().err == ""

    def test_hook_runs_validation_for_file_in_kb(self, tmp_path, monkeypatch, capsys):
        kb = self._setup_kb(tmp_path)
        monkeypatch.chdir(tmp_path)

        hook_json = {"tool_input": {"file_path": str(kb / "topic" / "note.md")}}
        with mock.patch("validate_kb._read_hook_input", return_value=hook_json):
            with mock.patch("validate_kb._get_git_changed_files", return_value=[]):
                rc = main(["--hook", "--quiet"])
        assert rc == 2
        assert "index_coverage" in capsys.readouterr().err

    def test_hook_returns_0_when_kb_is_clean(self, tmp_path, monkeypatch, capsys):
        kb = self._setup_kb(tmp_path)
        monkeypatch.chdir(tmp_path)

        root_index = kb / "index.md"
        root_index.write_text(index("Root") + "\n- [Topic](topic/index.md)\n")
        (kb / "topic" / "index.md").write_text(
            index("Topic") + "\n- [Note](note.md)\n"
        )
        hook_json = {"tool_input": {"file_path": str(kb / "topic" / "note.md")}}
        with mock.patch("validate_kb._read_hook_input", return_value=hook_json):
            with mock.patch("validate_kb._get_git_changed_files", return_value=[]):
                rc = main(["--hook", "--quiet"])
        assert rc == 0
        assert capsys.readouterr().err == ""

    def test_hook_no_stdin_skips(self, tmp_path, monkeypatch):
        self._setup_kb(tmp_path)
        monkeypatch.chdir(tmp_path)

        with mock.patch("validate_kb._read_hook_input", return_value=None):
            with mock.patch("validate_kb._get_git_changed_files", return_value=[]):
                rc = main(["--hook", "--quiet"])
        assert rc == 2  # No file filter — runs full validation, finds errors

    def test_hook_no_config_returns_0(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        hook_json = {"tool_input": {"file_path": "/some/file.md"}}
        with mock.patch("validate_kb._read_hook_input", return_value=hook_json):
            rc = main(["--hook", "--quiet"])
        assert rc == 0

    def test_hook_errors_to_stderr(self, tmp_path, monkeypatch, capsys):
        kb = self._setup_kb(tmp_path)
        monkeypatch.chdir(tmp_path)

        hook_json = {"tool_input": {"file_path": str(kb / "topic" / "note.md")}}
        with mock.patch("validate_kb._read_hook_input", return_value=hook_json):
            with mock.patch("validate_kb._get_git_changed_files", return_value=[]):
                main(["--hook", "--quiet"])
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err != ""

    def test_hook_warnings_also_trigger_exit_2(self, tmp_path, monkeypatch, capsys):
        kb = self._setup_kb(tmp_path)
        monkeypatch.chdir(tmp_path)

        (kb / "topic" / "index.md").write_text(
            index("Topic") + "\n- [Note](note.md)\n- [Other](other.md)\n"
        )
        (kb / "topic" / "other.md").write_text(note("Other"))
        other_topic = kb / "other-topic"
        other_topic.mkdir()
        (other_topic / "index.md").write_text(index("Other Topic"))
        (other_topic / "orphan.md").write_text(note("Orphan"))

        hook_json = {"tool_input": {"file_path": str(other_topic / "orphan.md")}}
        with mock.patch("validate_kb._read_hook_input", return_value=hook_json):
            with mock.patch("validate_kb._get_git_changed_files", return_value=[]):
                rc = main(["--hook", "--quiet"])
        assert rc == 2


class TestHookModeMultiKB:
    def _setup_multi_kb(self, tmp_path):
        kb1 = tmp_path / "kb1"
        kb2 = tmp_path / "kb2"
        for kb in (kb1, kb2):
            topics = kb / "topic"
            topics.mkdir(parents=True)
            (topics / "index.md").write_text(index("Topic"))

        config_dir = tmp_path / ".claude" / "knowledge-base"
        config_dir.mkdir(parents=True)
        (config_dir / "config.json").write_text(
            '{"kb_roots": [{"name": "core", "path": "./kb1"},{"name": "ios", "path": "./kb2"}]}'
        )
        return kb1, kb2

    def test_hook_file_in_first_kb_runs_validation(self, tmp_path, monkeypatch, capsys):
        kb1, kb2 = self._setup_multi_kb(tmp_path)
        monkeypatch.chdir(tmp_path)

        (kb1 / "topic" / "note.md").write_text(note("Note"))

        hook_json = {"tool_input": {"file_path": str(kb1 / "topic" / "note.md")}}
        with mock.patch("validate_kb._read_hook_input", return_value=hook_json):
            with mock.patch("validate_kb._get_git_changed_files", return_value=[]):
                rc = main(["--hook", "--quiet"])
        assert rc == 2
        assert "index_coverage" in capsys.readouterr().err

    def test_hook_file_in_second_kb_runs_validation(self, tmp_path, monkeypatch, capsys):
        kb1, kb2 = self._setup_multi_kb(tmp_path)
        monkeypatch.chdir(tmp_path)

        (kb2 / "topic" / "note.md").write_text(note("Note"))

        hook_json = {"tool_input": {"file_path": str(kb2 / "topic" / "note.md")}}
        with mock.patch("validate_kb._read_hook_input", return_value=hook_json):
            with mock.patch("validate_kb._get_git_changed_files", return_value=[]):
                rc = main(["--hook", "--quiet"])
        assert rc == 2

    def test_hook_file_outside_both_kbs_skips(self, tmp_path, monkeypatch, capsys):
        self._setup_multi_kb(tmp_path)
        monkeypatch.chdir(tmp_path)

        hook_json = {"tool_input": {"file_path": str(tmp_path / "unrelated" / "file.md")}}
        with mock.patch("validate_kb._read_hook_input", return_value=hook_json):
            with mock.patch("validate_kb._get_git_changed_files", return_value=[]):
                rc = main(["--hook", "--quiet"])
        assert rc == 0
        assert capsys.readouterr().err == ""

    def test_hook_validates_cross_kb_links(self, tmp_path, monkeypatch, capsys):
        kb1, kb2 = self._setup_multi_kb(tmp_path)
        monkeypatch.chdir(tmp_path)

        (kb1 / "topic" / "index.md").write_text(
            index("Topic") + "\nSee [@nonexistent/note.md](@nonexistent/note.md).\n"
        )

        hook_json = {"tool_input": {"file_path": str(kb1 / "topic" / "index.md")}}
        with mock.patch("validate_kb._read_hook_input", return_value=hook_json):
            with mock.patch("validate_kb._get_git_changed_files", return_value=[]):
                rc = main(["--hook", "--quiet"])
        assert rc == 2
        assert "unknown_cross_kb" in capsys.readouterr().err

    def test_hook_validates_cross_kb_escape(self, tmp_path, monkeypatch, capsys):
        kb1, kb2 = self._setup_multi_kb(tmp_path)
        monkeypatch.chdir(tmp_path)

        (kb1 / "topic" / "index.md").write_text(
            index("Topic") + "\nSee [other](../../../kb2/topic/index.md).\n"
        )

        hook_json = {"tool_input": {"file_path": str(kb1 / "topic" / "index.md")}}
        with mock.patch("validate_kb._read_hook_input", return_value=hook_json):
            with mock.patch("validate_kb._get_git_changed_files", return_value=[]):
                rc = main(["--hook", "--quiet"])
        assert rc == 2
        assert "cross_kb_escape" in capsys.readouterr().err

    def test_without_hook_still_returns_1(self, tmp_path, monkeypatch, capsys):
        kb1, kb2 = self._setup_multi_kb(tmp_path)
        monkeypatch.chdir(tmp_path)

        (kb1 / "topic" / "note.md").write_text(note("Note"))

        with mock.patch("validate_kb._get_git_changed_files", return_value=[]):
            rc = main(["--quiet"])
        assert rc == 1  # Not 2 — old behavior preserved
