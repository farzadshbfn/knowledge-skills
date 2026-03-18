"""Integration tests — full validate_kb runs, edge cases, filesystem exclusion."""

from unittest import mock

from validate_kb import MockFileSystem, RealFileSystem, validate_kb
from learn_helpers import note, index, project_agent, skill

class TestValidateKb:
    def test_valid_kb_no_issues(self, valid_kb):
        result = validate_kb("kb", fs=valid_kb, agent_root=".claude/agents")
        real_errors = [e for e in result.errors if e.check != "read_error"]
        assert real_errors == [], f"Unexpected errors: {real_errors}"

    def test_valid_kb_stats(self, valid_kb):
        result = validate_kb("kb", fs=valid_kb, agent_root=".claude/agents")
        s = result.stats
        assert s.topic_notes == 1
        assert s.index_notes == 3
        assert s.skill_files == 1
        assert s.agent_files == 2
        assert s.reference_files == 1
        assert s.asset_files == 1

    def test_broken_kb_catches_errors(self, broken_kb):
        result = validate_kb("kb", fs=broken_kb, agent_root=".claude/agents")
        checks_found = {i.check for i in result.issues}
        assert "frontmatter_missing" in checks_found
        assert "missing_field" in checks_found
        assert "broken_link" in checks_found
        assert "wikilink" in checks_found
        assert "oversized_note" in checks_found
        assert "skill_exclusivity" in checks_found
        assert "skill_scope" in checks_found

    def test_broken_kb_skill_without_hint_no_error(self, broken_kb):
        """argument-hint is optional for skills — no missing_field error."""
        result = validate_kb("kb", fs=broken_kb, agent_root=".claude/agents")
        skill_issues = [i for i in result.issues if "SKILL.md" in i.file]
        assert not any("argument-hint" in i.message for i in skill_issues)

    def test_broken_kb_agent_unknown_model(self, broken_kb):
        result = validate_kb("kb", fs=broken_kb, agent_root=".claude/agents")
        agent_issues = [i for i in result.issues if "bad-agent" in i.file]
        assert any(i.check == "unknown_model" for i in agent_issues)

    def test_broken_kb_agent_invalid_background(self, broken_kb):
        result = validate_kb("kb", fs=broken_kb, agent_root=".claude/agents")
        agent_issues = [i for i in result.issues if "bad-agent" in i.file]
        assert any(i.check == "invalid_background" for i in agent_issues)

    def test_broken_kb_skill_broken_link(self, broken_kb):
        result = validate_kb("kb", fs=broken_kb, agent_root=".claude/agents")
        skill_broken = [i for i in result.issues if "bad-scope.md" in i.file and i.check == "broken_link"]
        assert len(skill_broken) == 1
        assert "nonexistent.md" in skill_broken[0].message

    def test_broken_kb_unexpected_field(self, broken_kb):
        result = validate_kb("kb", fs=broken_kb, agent_root=".claude/agents")
        orphan_issues = [i for i in result.issues if "orphan.md" in i.file]
        assert any(i.check == "unexpected_field" and "tags" in i.message for i in orphan_issues)

    def test_broken_kb_code_block_links_ignored(self, broken_kb):
        result = validate_kb("kb", fs=broken_kb, agent_root=".claude/agents")
        code_note_broken = [i for i in result.issues if i.file == "topic-b/code-note.md" and i.check == "broken_link"]
        assert not any("fake.md" in i.message for i in code_note_broken)

    def test_missing_toc_detected(self, broken_kb):
        result = validate_kb("kb", fs=broken_kb, agent_root=".claude/agents")
        assert any("long-no-toc" in i.file for i in result.issues if i.check == "missing_toc")

class TestEdgeCases:
    def test_empty_kb(self):
        result = validate_kb("kb", fs=MockFileSystem({}))
        assert result.errors == []
        assert result.stats.total_notes == 0

    def test_single_root_index(self):
        fs = MockFileSystem({"kb/index.md": index()})
        result = validate_kb("kb", fs=fs)
        assert [e for e in result.errors if e.check != "read_error"] == []

    def test_deeply_nested_note(self):
        fs = MockFileSystem({
            "kb/index.md": index() + "\n- [sub](a/index.md)\n",
            "kb/a/index.md": index("A") + "\n- [b](b/index.md)\n",
            "kb/a/b/index.md": index("B") + "\n- [note](note.md)\n",
            "kb/a/b/note.md": note("Deep Note"),
        })
        assert [e for e in validate_kb("kb", fs=fs).errors if e.check != "read_error"] == []

    def test_agent_without_kb(self):
        from learn_helpers import project_agent
        fs = MockFileSystem({".claude/agents/test.md": project_agent()})
        result = validate_kb("kb", fs=fs, agent_root=".claude/agents")
        assert result.stats.agent_files == 1

class TestRealFileSystemExclusion:
    def _populate(self, tmp_path):
        valid = ["topic/index.md", "topic/note.md", ".claude/agents/sync.md"]
        excluded = [
            ".venv/lib/readme.md", ".pycharm/config.md", "__pycache__/cached.md",
            "__pytest_cache__/readme.md", ".hidden/secret.md",
            "topic/__pycache__/stale.md",
        ]
        for rel in valid + excluded:
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("---\nname: test\n---\n")
        return valid

    def test_excludes_dot_prefixed_dirs(self, tmp_path):
        self._populate(tmp_path)
        files = RealFileSystem().list_md_files(str(tmp_path))
        assert not any(".venv" in f or ".pycharm" in f or ".hidden" in f for f in files)

    def test_excludes_dunder_prefixed_dirs(self, tmp_path):
        self._populate(tmp_path)
        files = RealFileSystem().list_md_files(str(tmp_path))
        assert not any("__pycache__" in f or "__pytest_cache__" in f for f in files)

    def test_allows_dot_claude(self, tmp_path):
        self._populate(tmp_path)
        assert any(".claude" in f for f in RealFileSystem().list_md_files(str(tmp_path)))

    def test_includes_valid_files(self, tmp_path):
        valid = self._populate(tmp_path)
        assert set(RealFileSystem().list_md_files(str(tmp_path))) == set(valid)
