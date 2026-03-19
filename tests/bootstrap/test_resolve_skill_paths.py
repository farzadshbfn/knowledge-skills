"""Tests for resolve_skill_paths — skill location and script path resolution."""

from pathlib import Path

from resolve_skill_paths import find_skills_location, main


def _create_skills(base: Path, with_monitor: bool = True):
    """Create minimal skill directories with expected scripts."""
    skills_dir = base / ".claude" / "skills"
    learn_scripts = skills_dir / "kb-learn" / "scripts"
    learn_scripts.mkdir(parents=True)
    (learn_scripts / "validate_kb.py").write_text("# validator")
    if with_monitor:
        monitor_scripts = skills_dir / "kb-monitor" / "scripts"
        monitor_scripts.mkdir(parents=True)
        (monitor_scripts / "track_kb_access.py").write_text("# tracker")
        (monitor_scripts / "analyze_access.py").write_text("# analyzer")
    return skills_dir


class TestFindSkillsLocation:
    def test_project_local(self, tmp_path):
        skills_dir = _create_skills(tmp_path)
        assert find_skills_location(tmp_path) == skills_dir

    def test_only_needs_kb_learn(self, tmp_path):
        skills_dir = _create_skills(tmp_path, with_monitor=False)
        assert find_skills_location(tmp_path) == skills_dir

    def test_no_kb_learn_returns_none(self, tmp_path):
        skills_dir = tmp_path / ".claude" / "skills" / "kb-monitor"
        skills_dir.mkdir(parents=True)
        assert find_skills_location(tmp_path) is None

    def test_no_skills_dir(self, tmp_path):
        assert find_skills_location(tmp_path) is None

    def test_empty_skills_dir(self, tmp_path):
        (tmp_path / ".claude" / "skills").mkdir(parents=True)
        assert find_skills_location(tmp_path) is None


class TestMain:
    def test_full_install(self, tmp_path):
        _create_skills(tmp_path)
        result = main(tmp_path)
        assert result is not None
        assert result["validation"] is not None
        assert result["monitoring"]["track_kb_access"] is not None
        assert result["monitoring"]["analyze_access"] is not None

    def test_no_monitor(self, tmp_path):
        _create_skills(tmp_path, with_monitor=False)
        result = main(tmp_path)
        assert result is not None
        assert result["validation"] is not None
        assert result["monitoring"]["track_kb_access"] is None
        assert result["monitoring"]["analyze_access"] is None

    def test_no_kb_learn_returns_none(self, tmp_path):
        assert main(tmp_path) is None

    def test_missing_validate_script_returns_none(self, tmp_path):
        """kb-learn dir exists but validate_kb.py is missing."""
        skills_dir = tmp_path / ".claude" / "skills" / "kb-learn"
        skills_dir.mkdir(parents=True)
        assert main(tmp_path) is None

    def test_resolved_paths_are_absolute(self, tmp_path):
        _create_skills(tmp_path)
        result = main(tmp_path)
        assert Path(result["validation"]).is_absolute()
        assert Path(result["monitoring"]["track_kb_access"]).is_absolute()
        assert Path(result["monitoring"]["analyze_access"]).is_absolute()

    def test_resolves_symlinks(self, tmp_path):
        actual = tmp_path / "actual"
        _create_skills(actual)
        project = tmp_path / "project"
        claude_dir = project / ".claude"
        claude_dir.mkdir(parents=True)
        (claude_dir / "skills").symlink_to(actual / ".claude" / "skills")
        result = main(project)
        assert result is not None
        assert "project/.claude/skills" in result["skills_dir"]
        # Scripts resolve through symlinks
        assert "actual" in result["validation"]
