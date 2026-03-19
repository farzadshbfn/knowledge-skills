"""Tests for structural checks — orphans, sizes, TOC, skill constraints, indexes."""

from validate_kb import (
    check_index_coverage, check_missing_index, check_note_sizes,
    check_orphans, check_skill_exclusivity, check_skill_scope, check_toc,
)
from learn_helpers import note, index, reference, skill, skill_agent, asset

class TestCheckOrphans:
    def test_no_orphans(self):
        files = {
            "index.md": "See [topic](topic/index.md).",
            "topic/index.md": "See [note](note.md).",
            "topic/note.md": "Content.",
        }
        assert check_orphans(files) == []

    def test_orphan_detected(self):
        files = {
            "index.md": "Root.",
            "topic/index.md": "Topic.",
            "topic/note.md": "Orphan content.",
        }
        orphan_files = {i.file for i in check_orphans(files)}
        assert "topic/note.md" in orphan_files

    def test_root_index_exempt(self):
        assert check_orphans({"index.md": "Root."}) == []

    def test_skill_files_excluded(self):
        files = {"index.md": "Root.", "topic/skill/SKILL.md": "Not checked."}
        assert check_orphans(files) == []

    def test_basename_match_counts(self):
        files = {"index.md": "See [note](topic/note.md).", "topic/note.md": "Content."}
        assert check_orphans(files) == []

class TestCheckNoteSizes:
    def test_within_limit(self):
        assert check_note_sizes({"note.md": "short\n" * 100}) == []

    def test_at_limit(self):
        assert check_note_sizes({"note.md": "line\n" * 500}) == []

    def test_over_limit(self):
        issues = check_note_sizes({"note.md": "line\n" * 501})
        assert len(issues) == 1
        assert issues[0].check == "oversized_note"

    def test_custom_limit(self):
        assert len(check_note_sizes({"note.md": "line\n" * 11}, max_lines=10)) == 1

    def test_changelog_exempt(self):
        """CHANGELOG.md is exempt from the size limit — it grows indefinitely."""
        assert check_note_sizes({"CHANGELOG.md": "line\n" * 1000}) == []

    def test_changelog_exempt_with_kb_prefix(self):
        """CHANGELOG.md at any KB root path is exempt."""
        files = {
            "CHANGELOG.md": "line\n" * 800,
            "note.md": "line\n" * 501,
        }
        issues = check_note_sizes(files)
        assert len(issues) == 1
        assert issues[0].file == "note.md"

class TestCheckToc:
    def test_short_note_no_toc_needed(self):
        files = {"topic/note.md": "---\nname: N\ndescription: D\n---\n\n# Note\n\n" + "x\n" * 50}
        assert check_toc(files, check_scope={"topic/note.md"}) == []

    def test_long_note_with_toc(self):
        content = "---\nname: N\ndescription: D\n---\n\n# Note\n\n## Contents\n\n" + "x\n" * 120
        assert check_toc({"topic/note.md": content}, check_scope={"topic/note.md"}) == []

    def test_long_note_without_toc(self):
        content = "---\nname: N\ndescription: D\n---\n\n# Note\n\n## Overview\n\n" + "x\n" * 120
        issues = check_toc({"topic/note.md": content}, check_scope={"topic/note.md"})
        assert len(issues) == 1
        assert issues[0].check == "missing_toc"

    def test_non_topic_excluded(self):
        content = "---\ndate: 2026-01-01\n---\n\n# Log\n\n" + "x\n" * 120
        assert check_toc({"logs/long-log.md": content}, check_scope=set()) == []

class TestCheckSkillExclusivity:
    def test_skill_folder_with_only_index(self):
        files = {"topic/index.md": index(), "topic/skill/SKILL.md": skill()}
        assert check_skill_exclusivity(files) == []

    def test_skill_folder_with_extra_topic_note(self):
        files = {
            "topic/index.md": index(),
            "topic/extra-note.md": note("Extra"),
            "topic/skill/SKILL.md": skill(),
        }
        issues = check_skill_exclusivity(files)
        assert len(issues) == 1
        assert issues[0].check == "skill_exclusivity"
        assert "extra-note.md" in issues[0].file

    def test_no_skill_folder_multiple_notes(self):
        files = {
            "topic/index.md": index(),
            "topic/note-one.md": note("One"),
            "topic/note-two.md": note("Two"),
        }
        assert check_skill_exclusivity(files) == []

class TestCheckSkillScope:
    def test_link_to_sibling_in_skill(self):
        files = {
            "topic/skill/SKILL.md": "See [ref](reference/workflow.md).",
            "topic/skill/reference/workflow.md": reference(),
        }
        assert check_skill_scope(files) == []

    def test_link_outside_skill_folder(self):
        files = {
            "topic/skill/reference/folder.md": "See [index](../../index.md).",
            "topic/index.md": index(),
        }
        issues = check_skill_scope(files)
        assert len(issues) == 1
        assert issues[0].check == "skill_scope"

    def test_link_to_other_skill_file_via_parent(self):
        files = {
            "topic/skill/agents/scout.md": "See [ref](../reference/workflow.md).",
            "topic/skill/reference/workflow.md": reference(),
        }
        assert check_skill_scope(files) == []

class TestCheckMissingIndex:
    def test_no_issues_when_all_folders_have_index(self):
        files = {
            "index.md": index("Root"),
            "topic-a/index.md": index("Topic A"),
            "topic-a/note.md": note("Note"),
            "topic-b/index.md": index("Topic B"),
        }
        assert check_missing_index(files) == []

    def test_detects_missing_index(self):
        issues = check_missing_index({"topic-a/note.md": note("Note")})
        missing = {i.file for i in issues if i.check == "missing_index"}
        assert "topic-a" in missing

    def test_skill_folder_accepts_skill_md(self):
        files = {
            "index.md": index(),
            "topic-a/index.md": index(),
            "topic-a/skill/SKILL.md": skill(),
        }
        assert check_missing_index(files) == []

    def test_skill_folder_missing_skill_md(self):
        files = {
            "index.md": index(),
            "topic-a/index.md": index(),
            "topic-a/skill/readme.md": "# Readme",
        }
        issues = check_missing_index(files)
        skill_issues = [i for i in issues if "skill" in i.file and i.file.endswith("skill")]
        assert len(skill_issues) == 1
        assert skill_issues[0].level == "warning"

    def test_skill_subdirs_exempt(self):
        files = {
            "index.md": index(),
            "topic-a/index.md": index(),
            "topic-a/skill/SKILL.md": skill(),
            "topic-a/skill/agents/scout.md": skill_agent(),
            "topic-a/skill/reference/workflow.md": reference(),
            "topic-a/skill/assets/template.md": asset(),
        }
        assert check_missing_index(files) == []

    def test_ignores_non_topic_files(self):
        from learn_helpers import project_agent
        files = {"CHANGELOG.md": "# Changelog", ".claude/agents/sync.md": project_agent()}
        assert check_missing_index(files) == []

    def test_hyphenated_index_accepted(self):
        files = {
            "index.md": index(),
            "topic-a/topic-a-index.md": index(),
            "topic-a/note.md": note("Note"),
        }
        assert check_missing_index(files) == []

    def test_nested_folders(self):
        files = {
            "index.md": index(),
            "topic-a/index.md": index(),
            "topic-a/sub/index.md": index("Sub"),
            "topic-a/sub/note.md": note("Note"),
        }
        assert check_missing_index(files) == []

    def test_nested_folder_missing_index(self):
        files = {
            "index.md": index(),
            "topic-a/index.md": index(),
            "topic-a/sub/note.md": note("Note"),
        }
        issues = check_missing_index(files)
        assert len(issues) == 1
        assert "topic-a/sub" in issues[0].file

    def test_root_missing_index_when_subfolders_exist(self):
        """KB root needs index.md when it has subfolders."""
        files = {
            "characters/index.md": index("Characters"),
            "characters/dino.md": note("Dino"),
            "gemini/index.md": index("Gemini"),
            "gemini/note.md": note("Note"),
        }
        issues = check_missing_index(files)
        assert len(issues) == 1
        assert issues[0].file == "."
        assert issues[0].check == "missing_index"

    def test_parent_folder_with_subfolders_and_index_ok(self):
        """ with index.md and subfolders passes."""
        files = {
            "index.md": index("Root"),
            "characters/index.md": index("Characters"),
            "characters/dino.md": note("Dino"),
        }
        assert check_missing_index(files) == []

class TestCheckIndexCoverage:
    def test_no_issues_when_all_linked(self):
        files = {
            "topic-a/index.md": index("Topic A") + "\n- [Note](note.md)\n- [Sub](sub/index.md)\n",
            "topic-a/note.md": note("Note"),
            "topic-a/sub/index.md": index("Sub"),
        }
        assert check_index_coverage(files) == []

    def test_missing_sibling_link(self):
        files = {"topic-a/index.md": index("Topic A"), "topic-a/note.md": note("Note")}
        sibling_issues = [i for i in check_index_coverage(files) if "sibling" in i.message]
        assert len(sibling_issues) == 1
        assert sibling_issues[0].level == "error"

    def test_missing_subfolder_link(self):
        files = {
            "topic-a/index.md": index("Topic A"),
            "topic-a/sub/index.md": index("Sub"),
            "topic-a/sub/note.md": note("Note"),
        }
        folder_issues = [i for i in check_index_coverage(files) if i.file == "topic-a/index.md" and "subfolder" in i.message]
        assert len(folder_issues) == 1

    def test_skill_md_accepted_for_subfolder(self):
        files = {
            "topic-a/index.md": index("Topic A") + "\n- [Skill](skill/SKILL.md)\n",
            "topic-a/skill/SKILL.md": skill("topic-a"),
        }
        folder_issues = [i for i in check_index_coverage(files) if i.file == "topic-a/index.md" and "subfolder" in i.message]
        assert folder_issues == []

    def test_cross_kb_links_ignored(self):
        files = {"topic-a/index.md": index("Topic A") + "\n- [Other KB](@ios/note.md)\n"}
        assert check_index_coverage(files) == []

    def test_skill_md_checks_coverage_too(self):
        files = {
            "topic-a/skill/SKILL.md": skill("topic-a") + "\n- [Scout](agents/scout.md)\n",
            "topic-a/skill/agents/scout.md": skill_agent(),
            "topic-a/skill/reference/workflow.md": reference(),
        }
        ref_issues = [i for i in check_index_coverage(files) if i.file.endswith("SKILL.md") and "reference" in i.message]
        assert len(ref_issues) == 1
        assert ref_issues[0].level == "warning"

    def test_multiple_siblings_missing(self):
        files = {
            "topic-a/index.md": index("Topic A"),
            "topic-a/note-1.md": note("Note 1"),
            "topic-a/note-2.md": note("Note 2"),
            "topic-a/note-3.md": note("Note 3"),
        }
        assert len([i for i in check_index_coverage(files) if "sibling" in i.message]) == 3

    def test_subfolder_only_counted_once(self):
        files = {
            "topic-a/index.md": index("Topic A"),
            "topic-a/sub/index.md": index("Sub"),
            "topic-a/sub/note-a.md": note("A"),
            "topic-a/sub/note-b.md": note("B"),
        }
        folder_issues = [i for i in check_index_coverage(files) if i.file == "topic-a/index.md" and "subfolder" in i.message]
        assert len(folder_issues) == 1
