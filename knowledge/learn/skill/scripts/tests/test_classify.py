"""Tests for file classification logic."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validate_kb import ASSET, TOPIC, INDEX, PROJECT_AGENT, REFERENCE, SKILL, SKILL_AGENT, UNKNOWN, classify_file


class TestClassifyFile:
    def test_topic_note(self):
        assert classify_file("topic/note.md") == TOPIC

    def test_nested_note(self):
        assert classify_file("writing/ai-patterns/note.md") == TOPIC

    def test_root_index(self):
        assert classify_file("index.md") == INDEX

    def test_topic_index(self):
        assert classify_file("topic/index.md") == INDEX

    def test_named_index(self):
        assert classify_file("topic/sub-index.md") == INDEX
        assert classify_file("topic/ai-writing-patterns-index.md") == INDEX
        assert classify_file("topic/index-guide.md") == TOPIC

    def test_skill_file(self):
        assert classify_file("topic/skill/SKILL.md") == SKILL

    def test_skill_agent(self):
        assert classify_file("topic/skill/agents/scout.md") == SKILL_AGENT

    def test_skill_asset(self):
        assert classify_file("topic/skill/assets/template.md") == ASSET

    def test_skill_reference(self):
        assert classify_file("topic/skill/reference/workflow.md") == REFERENCE

    def test_skill_references_plural(self):
        assert classify_file("topic/skill/references/craft.md") == REFERENCE

    def test_project_agent(self):
        assert classify_file(".claude/agents/sync.md") == PROJECT_AGENT

    def test_hidden_dir_unknown(self):
        assert classify_file(".obsidian/config.md") == UNKNOWN

    def test_skill_internal_script_unknown(self):
        assert classify_file("topic/skill/scripts/validate.md") == UNKNOWN
