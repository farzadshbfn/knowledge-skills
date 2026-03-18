#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pytest"]
# ///
"""Tests for kb_loader.py — KB structure loading for AI agents."""

import json
from pathlib import Path

import pytest
from kb_loader import (
    CategoryNode,
    KBConfig,
    KBEntry,
    KBStructure,
    MockFileSystem,
    MultiKBStructure,
    NoteMeta,
    RealFileSystem,
    build_category_tree,
    extract_meta,
    filter_topic,
    format_compact,
    format_list_topics,
    load_config,
    load_kb,
    load_multi_kb,
    node_to_dict,
    structure_to_dict,
)
from find_helpers import note, index, project_agent, reference, skill, skill_agent

# ===================================================================
# extract_meta
# ===================================================================

class TestExtractMeta:
    def test_basic(self):
        name, desc = extract_meta("---\nname: Test\ndescription: A desc.\n---\nBody")
        assert name == "Test"
        assert desc == "A desc."

    def test_no_frontmatter(self):
        name, desc = extract_meta("# Just a heading")
        assert name == ""
        assert desc == ""

    def test_missing_fields(self):
        name, desc = extract_meta("---\nname: Only Name\n---\n")
        assert name == "Only Name"
        assert desc == ""

    def test_quoted_values(self):
        name, desc = extract_meta('---\nname: "Quoted"\ndescription: \'Single\'\n---\n')
        assert name == "Quoted"
        assert desc == "Single"

# ===================================================================
# build_category_tree
# ===================================================================

class TestBuildCategoryTree:
    def test_empty(self):
        root = build_category_tree({})
        assert root.children == {}
        assert root.notes == []

    def test_single_topic(self):
        files = {
            "index.md": index("Root"),
            "topic/index.md": index("Topic"),
            "topic/note.md": note("Note"),
        }
        root = build_category_tree(files)
        assert root.index is not None
        assert root.index.name == "Root"
        assert "topic" in root.children
        topic_node = root.children["topic"]
        assert topic_node.index is not None
        assert topic_node.index.name == "Topic"
        assert len(topic_node.notes) == 1
        assert topic_node.notes[0].name == "Note"

    def test_nested_topics(self):
        files = {
            "index.md": index("Root"),
            "a/index.md": index("A"),
            "a/b/index.md": index("B"),
            "a/b/note.md": note("Deep Note"),
        }
        root = build_category_tree(files)
        assert "a" in root.children
        a_node = root.children["a"]
        assert "b" in a_node.children
        b_node = a_node.children["b"]
        assert len(b_node.notes) == 1
        assert b_node.notes[0].name == "Deep Note"

    def test_skill_captured(self):
        files = {
            "topic/index.md": index("Topic"),
            "topic/skill/SKILL.md": skill("topic", "A skill."),
            "topic/skill/agents/scout.md": skill_agent("scout"),
        }
        root = build_category_tree(files)
        topic_node = root.children["topic"]
        assert topic_node.skill is not None
        assert topic_node.skill.name == "topic"

    def test_skill_agent_not_in_notes(self):
        """Skill internal files (agents, assets, refs) should not appear as topic notes."""
        files = {
            "topic/index.md": index("Topic"),
            "topic/skill/SKILL.md": skill("topic"),
            "topic/skill/agents/scout.md": skill_agent("scout"),
            "topic/skill/reference/ref.md": reference(),
        }
        root = build_category_tree(files)
        topic_node = root.children["topic"]
        assert len(topic_node.notes) == 0

    def test_skill_folder_as_tree_node(self):
        """Skill folder should appear as a child node of the topic."""
        files = {
            "topic/index.md": index("Topic"),
            "topic/skill/SKILL.md": skill("topic"),
        }
        root = build_category_tree(files)
        topic_node = root.children["topic"]
        assert "skill" in topic_node.children
        skill_node = topic_node.children["skill"]
        assert skill_node.index is not None
        assert skill_node.index.name == "topic"

    def test_skill_subdirs_as_tree_children(self):
        """Skill subdirectories (agents/, reference/) appear as children of skill node."""
        files = {
            "topic/index.md": index("Topic"),
            "topic/skill/SKILL.md": skill("topic"),
            "topic/skill/agents/scout.md": skill_agent("scout"),
            "topic/skill/reference/ref.md": reference(),
        }
        root = build_category_tree(files)
        skill_node = root.children["topic"].children["skill"]
        assert "agents" in skill_node.children
        assert "reference" in skill_node.children
        agents_node = skill_node.children["agents"]
        assert len(agents_node.notes) == 1
        assert agents_node.notes[0].name == "scout"

    def test_skill_md_sets_parent_skill_badge(self):
        """SKILL.md should set .skill on the parent topic node for badge display."""
        files = {
            "topic/index.md": index("Topic"),
            "topic/skill/SKILL.md": skill("topic"),
        }
        root = build_category_tree(files)
        topic_node = root.children["topic"]
        assert topic_node.skill is not None
        assert topic_node.skill.name == "topic"

    def test_skill_folder_serialization(self):
        """Skill folder children should appear in serialized output."""
        files = {
            "topic/index.md": index("Topic"),
            "topic/skill/SKILL.md": skill("topic"),
            "topic/skill/agents/scout.md": skill_agent("scout"),
        }
        root = build_category_tree(files)
        d = node_to_dict(root)
        topic_d = d["children"]["topic"]
        assert "children" in topic_d
        assert "skill" in topic_d["children"]
        skill_d = topic_d["children"]["skill"]
        assert skill_d["index"]["name"] == "topic"
        assert "agents" in skill_d["children"]

    def test_changelog_excluded(self):
        files = {
            "topic/note.md": note("Note"),
            "CHANGELOG.md": "# Changelog",
        }
        root = build_category_tree(files)
        assert "topic" in root.children
        # CHANGELOG.md should not appear in tree
        assert not root.notes

# ===================================================================
# load_kb
# ===================================================================

class TestLoadKb:
    def test_full_load(self):
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/topic/index.md": index("Topic"),
            "kb/topic/note.md": note("Note"),
            "kb/topic/skill/SKILL.md": skill("topic-skill"),
            ".claude/agents/sync.md": project_agent("sync"),
        })
        result = load_kb("kb", fs=fs, agent_root=".claude/agents")

        assert result.total_files == 4  # KB files only (3 topic + 1 skill)
        assert len(result.skills) == 1
        assert result.skills[0].name == "topic-skill"
        assert len(result.agents) == 1
        assert result.agents[0].name == "sync"

    def test_empty_kb(self):
        fs = MockFileSystem({})
        result = load_kb("kb", fs=fs)
        assert result.total_files == 0
        assert result.tree is not None
        assert result.tree.children == {}

    def test_kb_name_default_empty(self):
        fs = MockFileSystem({})
        result = load_kb("kb", fs=fs)
        assert result.kb_name == ""

# ===================================================================
# Serialization
# ===================================================================

class TestSerialization:
    def test_node_to_dict(self):
        node = CategoryNode(
            path="",
            index=NoteMeta("index.md", "Root", "Root index"),
            children={
                "topic": CategoryNode(
                    path="topic",
                    index=NoteMeta("topic/index.md", "Topic", "Topic desc"),
                    notes=[NoteMeta("topic/note.md", "Note", "Note desc")],
                ),
            },
        )
        d = node_to_dict(node)
        assert d["path"] == ""
        assert d["index"]["name"] == "Root"
        assert "topic" in d["children"]
        assert len(d["children"]["topic"]["notes"]) == 1

    def test_node_to_dict_with_prefix(self):
        """Paths should be prefixed with kb_root/ when prefix provided."""
        node = CategoryNode(
            path="",
            index=NoteMeta("index.md", "Root", "Root index"),
            notes=[NoteMeta("note.md", "Note", "Desc")],
        )
        d = node_to_dict(node, path_prefix="./knowledge/")
        assert d["path"] == "./knowledge"
        assert d["index"]["path"] == "./knowledge/index.md"
        assert d["notes"][0]["path"] == "./knowledge/note.md"

    def test_structure_to_dict_json_serializable(self):
        s = KBStructure(
            kb_root="./knowledge",
            tree=CategoryNode(path=""),
            skills=[NoteMeta("skill.md", "sk", "desc")],
            agents=[],
            total_files=10,
        )
        d = structure_to_dict(s)
        # Should be JSON-serializable
        text = json.dumps(d)
        assert '"kb_root"' in text

    def test_structure_to_dict_prefixes_paths(self):
        """structure_to_dict should prefix paths with kb_root/."""
        s = KBStructure(
            kb_root="./knowledge",
            tree=CategoryNode(
                path="",
                index=NoteMeta("index.md", "Root", "Desc"),
            ),
            skills=[NoteMeta("topic/skill/SKILL.md", "sk", "desc")],
            agents=[],
            total_files=2,
        )
        d = structure_to_dict(s)
        assert d["tree"]["path"] == "./knowledge"
        assert d["tree"]["index"]["path"] == "./knowledge/index.md"
        assert d["skills"][0]["path"] == "./knowledge/topic/skill/SKILL.md"

    def test_structure_to_dict_agents_not_prefixed(self):
        """Agent paths should NOT be prefixed (they're outside KB root)."""
        s = KBStructure(
            kb_root="./knowledge",
            tree=CategoryNode(path=""),
            agents=[NoteMeta(".claude/agents/sync.md", "sync", "desc")],
            total_files=1,
        )
        d = structure_to_dict(s)
        assert d["agents"][0]["path"] == ".claude/agents/sync.md"

class TestFormatCompact:
    def test_compact_output(self):
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/topic/index.md": index("Topic"),
            "kb/topic/note.md": note("Note", "A note about something."),
        })
        result = load_kb("kb", fs=fs)
        multi = MultiKBStructure(kbs=[result])
        text = format_compact(multi)

        assert "KB:" in text
        assert "Root" in text
        assert "Topic" in text
        assert "Note" in text

# ===================================================================
# format_list_topics
# ===================================================================

class TestListTopics:
    def test_contains_topic_names(self):
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/topic-a/index.md": index("Topic A", "About topic A."),
            "kb/topic-b/index.md": index("Topic B", "About topic B."),
        })
        result = load_kb("kb", fs=fs)
        multi = MultiKBStructure(kbs=[result])
        text = format_list_topics(multi)
        assert "topic-a" in text
        assert "topic-b" in text
        assert "About topic A." in text

    def test_skill_marker(self):
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/topic-a/index.md": index("Topic A", "Desc."),
            "kb/topic-a/skill/SKILL.md": skill("topic-a"),
        })
        result = load_kb("kb", fs=fs)
        multi = MultiKBStructure(kbs=[result])
        text = format_list_topics(multi)
        assert "[skill]" in text

    def test_empty_tree(self):
        fs = MockFileSystem({})
        result = load_kb("kb", fs=fs)
        multi = MultiKBStructure(kbs=[result])
        text = format_list_topics(multi)
        assert "0 categories" in text

    def test_sorted_output(self):
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/zzz/index.md": index("ZZZ"),
            "kb/aaa/index.md": index("AAA"),
        })
        result = load_kb("kb", fs=fs)
        multi = MultiKBStructure(kbs=[result])
        text = format_list_topics(multi)
        assert text.index("aaa") < text.index("zzz")

# ===================================================================
# filter_topic
# ===================================================================

class TestTopicFilter:
    def test_returns_subtree(self):
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/topic-a/index.md": index("Topic A"),
            "kb/topic-a/note.md": note("Note"),
        })
        result = load_kb("kb", fs=fs)
        multi = MultiKBStructure(kbs=[result])
        out = filter_topic(multi, "topic-a")
        assert out is not None
        kb_name, d = out
        assert d["index"]["name"] == "Topic A"
        assert len(d["notes"]) == 1

    def test_includes_skill(self):
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/topic-a/index.md": index("Topic A"),
            "kb/topic-a/skill/SKILL.md": skill("topic-a"),
        })
        result = load_kb("kb", fs=fs)
        multi = MultiKBStructure(kbs=[result])
        out = filter_topic(multi, "topic-a")
        assert out is not None
        _, d = out
        assert "skill" in d

    def test_excludes_other_topics(self):
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/topic-a/index.md": index("Topic A"),
            "kb/topic-b/index.md": index("Topic B"),
        })
        result = load_kb("kb", fs=fs)
        multi = MultiKBStructure(kbs=[result])
        out = filter_topic(multi, "topic-a")
        assert out is not None
        _, d = out
        assert "topic-b" not in str(d)

    def test_nonexistent_topic(self):
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
        })
        result = load_kb("kb", fs=fs)
        multi = MultiKBStructure(kbs=[result])
        assert filter_topic(multi, "nope") is None

# ===================================================================
# load_config (multi-KB format)
# ===================================================================

class TestLoadConfig:
    def test_single_entry(self):
        fs = MockFileSystem({
            "cfg.json": '{"kb_roots": [{"name": "core", "path": "./knowledge"}]}',
        })
        config = load_config("cfg.json", fs=fs)
        assert len(config.entries) == 1
        assert config.entries[0].name == "core"
        assert config.entries[0].path == "./knowledge"

    def test_multiple_entries(self):
        fs = MockFileSystem({
            "cfg.json": json.dumps({
                "kb_roots": [
                    {"name": "core", "path": "./knowledge"},
                    {"name": "ios", "path": "./ios/knowledge"},
                ]
            }),
        })
        config = load_config("cfg.json", fs=fs)
        assert len(config.entries) == 2
        assert config.entries[0].name == "core"
        assert config.entries[1].name == "ios"

    def test_empty_config(self):
        fs = MockFileSystem({
            "cfg.json": '{"kb_roots": []}',
        })
        config = load_config("cfg.json", fs=fs)
        assert len(config.entries) == 0

# ===================================================================
# load_multi_kb
# ===================================================================

class TestLoadMultiKb:
    def test_single_kb(self):
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/topic/index.md": index("Topic"),
        })
        config = KBConfig(entries=[KBEntry("core", "kb")])
        multi = load_multi_kb(config, fs=fs)
        assert len(multi.kbs) == 1
        assert multi.kbs[0].kb_name == "core"
        assert multi.kbs[0].kb_root == "kb"

    def test_multiple_kbs(self):
        fs = MockFileSystem({
            "kb1/index.md": index("KB1 Root"),
            "kb1/topic-a/index.md": index("Topic A"),
            "kb2/index.md": index("KB2 Root"),
            "kb2/topic-b/index.md": index("Topic B"),
        })
        config = KBConfig(entries=[
            KBEntry("core", "kb1"),
            KBEntry("ios", "kb2"),
        ])
        multi = load_multi_kb(config, fs=fs)
        assert len(multi.kbs) == 2
        assert multi.kbs[0].kb_name == "core"
        assert multi.kbs[1].kb_name == "ios"
        # Each KB has its own topics
        assert "topic-a" in multi.kbs[0].tree.children
        assert "topic-b" in multi.kbs[1].tree.children

    def test_agents_not_loaded(self):
        """load_multi_kb does NOT load agents — they're orthogonal to KBs."""
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            ".claude/agents/sync.md": project_agent("sync"),
        })
        config = KBConfig(entries=[KBEntry("core", "kb")])
        multi = load_multi_kb(config, fs=fs)
        assert multi.kbs[0].agents == []

    def test_empty_kb_in_multi(self):
        fs = MockFileSystem({
            "kb1/index.md": index("KB1"),
            # kb2 is empty
        })
        config = KBConfig(entries=[
            KBEntry("core", "kb1"),
            KBEntry("empty", "kb2"),
        ])
        multi = load_multi_kb(config, fs=fs)
        assert len(multi.kbs) == 2
        assert multi.kbs[1].total_files == 0

# ===================================================================
# Multi-KB format_list_topics
# ===================================================================

class TestMultiKBListTopics:
    def test_topics_grouped_by_kb(self):
        fs = MockFileSystem({
            "kb1/index.md": index("Root1"),
            "kb1/topic-a/index.md": index("Topic A", "About A."),
            "kb2/index.md": index("Root2"),
            "kb2/topic-b/index.md": index("Topic B", "About B."),
        })
        config = KBConfig(entries=[
            KBEntry("core", "kb1"),
            KBEntry("ios", "kb2"),
        ])
        multi = load_multi_kb(config, fs=fs)
        text = format_list_topics(multi)
        assert "@core" in text
        assert "@ios" in text
        assert "topic-a" in text
        assert "topic-b" in text

    def test_empty_kb_skipped(self):
        fs = MockFileSystem({
            "kb1/index.md": index("Root1"),
            "kb1/topic-a/index.md": index("Topic A", "About A."),
            # kb2 is empty
        })
        config = KBConfig(entries=[
            KBEntry("core", "kb1"),
            KBEntry("empty", "kb2"),
        ])
        multi = load_multi_kb(config, fs=fs)
        text = format_list_topics(multi)
        assert "@core" in text
        assert "@empty" not in text

    def test_single_kb_still_labeled(self):
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/topic/index.md": index("Topic", "Desc."),
        })
        config = KBConfig(entries=[KBEntry("core", "kb")])
        multi = load_multi_kb(config, fs=fs)
        text = format_list_topics(multi)
        assert "@core" in text

# ===================================================================
# Multi-KB filter_topic
# ===================================================================

class TestMultiKBFilterTopic:
    def test_config_order_precedence(self):
        """Same topic name in multiple KBs — config-order first wins."""
        fs = MockFileSystem({
            "kb1/index.md": index("Root1"),
            "kb1/shared/index.md": index("Shared from Core", "Core version."),
            "kb2/index.md": index("Root2"),
            "kb2/shared/index.md": index("Shared from iOS", "iOS version."),
        })
        config = KBConfig(entries=[
            KBEntry("core", "kb1"),
            KBEntry("ios", "kb2"),
        ])
        multi = load_multi_kb(config, fs=fs)
        out = filter_topic(multi, "shared")
        assert out is not None
        kb_name, d = out
        assert kb_name == "core"
        assert d["index"]["name"] == "Shared from Core"

    def test_returns_kb_name(self):
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/topic/index.md": index("Topic"),
        })
        config = KBConfig(entries=[KBEntry("core", "kb")])
        multi = load_multi_kb(config, fs=fs)
        out = filter_topic(multi, "topic")
        assert out is not None
        kb_name, _ = out
        assert kb_name == "core"

    def test_finds_in_second_kb(self):
        fs = MockFileSystem({
            "kb1/index.md": index("Root1"),
            "kb2/index.md": index("Root2"),
            "kb2/only-here/index.md": index("Only Here"),
        })
        config = KBConfig(entries=[
            KBEntry("core", "kb1"),
            KBEntry("ios", "kb2"),
        ])
        multi = load_multi_kb(config, fs=fs)
        out = filter_topic(multi, "only-here")
        assert out is not None
        kb_name, _ = out
        assert kb_name == "ios"

    def test_not_found_in_any_kb(self):
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
        })
        config = KBConfig(entries=[KBEntry("core", "kb")])
        multi = load_multi_kb(config, fs=fs)
        assert filter_topic(multi, "nope") is None

# ===================================================================
# Multi-KB output paths
# ===================================================================

class TestMultiKBOutputPaths:
    def test_paths_are_project_root_relative(self):
        """Output paths should be prefixed with kb_root/."""
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/topic/index.md": index("Topic"),
            "kb/topic/note.md": note("Note"),
        })
        config = KBConfig(entries=[KBEntry("core", "kb")])
        multi = load_multi_kb(config, fs=fs)
        out = filter_topic(multi, "topic")
        assert out is not None
        _, d = out
        assert d["path"].startswith("kb/")
        assert d["index"]["path"].startswith("kb/")
        assert d["notes"][0]["path"].startswith("kb/")

# ===================================================================
# @kb-name targeting via filter_topic
# ===================================================================

class TestKBNameTargeting:
    def test_at_kb_name_filters_to_single_kb(self):
        """@kb-name/topic syntax targets a specific KB, replacing old --kb-name flag."""
        fs = MockFileSystem({
            "cfg.json": json.dumps({
                "kb_roots": [
                    {"name": "core", "path": "kb1"},
                    {"name": "ios", "path": "kb2"},
                ]
            }),
            "kb1/index.md": index("Root1"),
            "kb1/topic-a/index.md": index("Topic A"),
            "kb2/index.md": index("Root2"),
            "kb2/topic-b/index.md": index("Topic B"),
        })
        config = load_config("cfg.json", fs=fs)
        multi = load_multi_kb(config, fs=fs)

        # @ios/topic-b targets ios KB specifically
        out = filter_topic(multi, "@ios/topic-b")
        assert out is not None
        kb_name, d = out
        assert kb_name == "ios"
        assert d["index"]["name"] == "Topic B"

        # @core/topic-a targets core KB specifically
        out = filter_topic(multi, "@core/topic-a")
        assert out is not None
        kb_name, d = out
        assert kb_name == "core"
        assert d["index"]["name"] == "Topic A"

        # @ios/topic-a doesn't exist in ios
        assert filter_topic(multi, "@ios/topic-a") is None

# ===================================================================
# RealFileSystem.list_md_files — directory exclusion
# ===================================================================

class TestRealFileSystemExclusion:
    """RealFileSystem.list_md_files must skip dot-prefixed and __-prefixed dirs."""

    def _populate(self, tmp_path):
        """Create a mix of valid and excluded .md files."""
        valid = [
            "topic/index.md",
            "topic/note.md",
        ]
        excluded = [
            ".venv/lib/readme.md",
            ".pycharm/config.md",
            "__pycache__/cached.md",
            "__pytest_cache__/readme.md",
            ".hidden/secret.md",
            "topic/__pycache__/stale.md",
        ]
        for rel in valid + excluded:
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("---\nname: test\n---\n")
        return valid

    def test_excludes_dot_prefixed_dirs(self, tmp_path):
        self._populate(tmp_path)
        fs = RealFileSystem()
        files = fs.list_md_files(str(tmp_path))
        assert not any(".venv" in f for f in files)
        assert not any(".pycharm" in f for f in files)
        assert not any(".hidden" in f for f in files)

    def test_excludes_dunder_prefixed_dirs(self, tmp_path):
        self._populate(tmp_path)
        fs = RealFileSystem()
        files = fs.list_md_files(str(tmp_path))
        assert not any("__pycache__" in f for f in files)
        assert not any("__pytest_cache__" in f for f in files)

    def test_includes_valid_files(self, tmp_path):
        valid = self._populate(tmp_path)
        fs = RealFileSystem()
        files = fs.list_md_files(str(tmp_path))
        assert set(files) == set(valid)

# ===================================================================
# format_list_topics with tree nesting
# ===================================================================

INFRA_FOLDERS = {"skill", "agents", "reference", "assets", "scripts", "legacy"}

class TestFormatListTopicsTree:
    def test_kb_name_as_parent(self):
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/topic/index.md": index("Topic"),
        })
        config = KBConfig(entries=[KBEntry("core", "kb")])
        multi = load_multi_kb(config, fs=fs)
        text = format_list_topics(multi)
        assert text.startswith("@core")

    def test_nested_topics_use_tree_lines(self):
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/parent/index.md": index("Parent"),
            "kb/parent/child-a/index.md": index("Child A"),
            "kb/parent/child-b/index.md": index("Child B"),
        })
        config = KBConfig(entries=[KBEntry("core", "kb")])
        multi = load_multi_kb(config, fs=fs)
        text = format_list_topics(multi)
        assert "├─" in text or "└─" in text
        assert "child-a" in text
        assert "child-b" in text

    def test_excludes_skill_folders_as_topics(self):
        """Infra folders must not appear as ├─/└─ topic entries."""
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/topic/index.md": index("Topic"),
            "kb/topic/skill/SKILL.md": skill("topic-skill", "A skill."),
            "kb/topic/skill/agents/scout.md": skill_agent("scout"),
            "kb/topic/skill/reference/ref.md": reference(),
        })
        config = KBConfig(entries=[KBEntry("core", "kb")])
        multi = load_multi_kb(config, fs=fs)
        text = format_list_topics(multi)
        for line in text.strip().split("\n"):
            if "─ " in line:
                topic_part = line.split("─ ")[-1].split(" —")[0].split(" [")[0].strip()
                assert topic_part not in INFRA_FOLDERS

    def test_skill_internals_shown_as_detail_lines(self):
        """Skill sub-folders should appear as ╰ lines under their topic."""
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/topic/index.md": index("Topic"),
            "kb/topic/skill/SKILL.md": skill("topic-skill", "A skill."),
            "kb/topic/skill/agents/scout.md": skill_agent("scout"),
            "kb/topic/skill/reference/ref.md": reference(),
        })
        config = KBConfig(entries=[KBEntry("core", "kb")])
        multi = load_multi_kb(config, fs=fs)
        text = format_list_topics(multi)
        assert "╰ agents/" in text
        assert "╰ reference/" in text

    def test_skill_detail_lines_use_filename_stems(self):
        """╰ lines should always use filename stems (not frontmatter names) in {a,b} format."""
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/topic/index.md": index("Topic"),
            "kb/topic/skill/SKILL.md": skill("topic-skill"),
            "kb/topic/skill/agents/scout.md": skill_agent("scout"),
            "kb/topic/skill/reference/deep-compaction.md": reference(),
        })
        config = KBConfig(entries=[KBEntry("core", "kb")])
        multi = load_multi_kb(config, fs=fs)
        text = format_list_topics(multi)
        assert "{scout}" in text
        assert "{deep-compaction}" in text

    def test_skill_detail_lines_indented_under_topic(self):
        """╰ lines should be indented more than their parent topic line."""
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/topic/index.md": index("Topic"),
            "kb/topic/skill/SKILL.md": skill("topic-skill"),
            "kb/topic/skill/agents/scout.md": skill_agent("scout"),
        })
        config = KBConfig(entries=[KBEntry("core", "kb")])
        multi = load_multi_kb(config, fs=fs)
        text = format_list_topics(multi)
        lines = text.strip().split("\n")
        topic_line = next(l for l in lines if "topic" in l and "─" in l)
        detail_line = next(l for l in lines if "╰" in l)
        assert len(detail_line) - len(detail_line.lstrip()) > len(topic_line) - len(topic_line.lstrip())

    def test_topic_without_skill_unchanged(self):
        """Topics without skills should not show any ╰ lines."""
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/topic/index.md": index("Topic"),
            "kb/topic/note.md": note("A Note"),
        })
        config = KBConfig(entries=[KBEntry("core", "kb")])
        multi = load_multi_kb(config, fs=fs)
        text = format_list_topics(multi)
        assert "╰" not in text

    def test_skill_folder_with_no_md_files_omitted(self):
        """A skill with no sub-folders containing .md files shows no ╰ lines."""
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/topic/index.md": index("Topic"),
            "kb/topic/skill/SKILL.md": skill("topic-skill"),
        })
        config = KBConfig(entries=[KBEntry("core", "kb")])
        multi = load_multi_kb(config, fs=fs)
        text = format_list_topics(multi)
        assert "╰" not in text

    def test_deep_nesting_indentation(self):
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/l1/index.md": index("L1"),
            "kb/l1/l2/index.md": index("L2"),
            "kb/l1/l2/l3/index.md": index("L3"),
        })
        config = KBConfig(entries=[KBEntry("core", "kb")])
        multi = load_multi_kb(config, fs=fs)
        text = format_list_topics(multi)
        lines = text.strip().split("\n")
        l2_line = next(l for l in lines if "l2" in l)
        l3_line = next(l for l in lines if "l3" in l)
        # l3 deeper than l2
        assert len(l3_line) - len(l3_line.lstrip()) > len(l2_line) - len(l2_line.lstrip())

    def test_last_child_uses_corner(self):
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/parent/index.md": index("Parent"),
            "kb/parent/only-child/index.md": index("Only Child"),
        })
        config = KBConfig(entries=[KBEntry("core", "kb")])
        multi = load_multi_kb(config, fs=fs)
        text = format_list_topics(multi)
        child_line = next(l for l in text.split("\n") if "only-child" in l)
        assert "└─" in child_line

    def test_multi_kb_separate_roots(self):
        fs = MockFileSystem({
            "kb1/index.md": index("Root1"),
            "kb1/topic-a/index.md": index("A"),
            "kb2/index.md": index("Root2"),
            "kb2/topic-b/index.md": index("B"),
        })
        config = KBConfig(entries=[
            KBEntry("core", "kb1"),
            KBEntry("ios", "kb2"),
        ])
        multi = load_multi_kb(config, fs=fs)
        text = format_list_topics(multi)
        assert "@core" in text
        assert "@ios" in text

# ===================================================================
# filter_topic with slash paths
# ===================================================================

class TestFilterTopicSlashPath:
    def test_slash_path_nested(self):
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/parent/index.md": index("Parent"),
            "kb/parent/child/index.md": index("Child", "Child desc."),
        })
        config = KBConfig(entries=[KBEntry("core", "kb")])
        multi = load_multi_kb(config, fs=fs)
        out = filter_topic(multi, "parent/child")
        assert out is not None
        _, d = out
        assert d["index"]["name"] == "Child"

    def test_slash_path_deep(self):
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/a/index.md": index("A"),
            "kb/a/b/index.md": index("B"),
            "kb/a/b/c/index.md": index("C"),
        })
        config = KBConfig(entries=[KBEntry("core", "kb")])
        multi = load_multi_kb(config, fs=fs)
        out = filter_topic(multi, "a/b/c")
        assert out is not None
        _, d = out
        assert d["index"]["name"] == "C"

    def test_slash_path_not_found(self):
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/parent/index.md": index("Parent"),
        })
        config = KBConfig(entries=[KBEntry("core", "kb")])
        multi = load_multi_kb(config, fs=fs)
        assert filter_topic(multi, "parent/nope") is None

    def test_simple_name_still_works(self):
        fs = MockFileSystem({
            "kb/index.md": index("Root"),
            "kb/topic/index.md": index("Topic"),
        })
        config = KBConfig(entries=[KBEntry("core", "kb")])
        multi = load_multi_kb(config, fs=fs)
        out = filter_topic(multi, "topic")
        assert out is not None

    def test_slash_path_multi_kb(self):
        fs = MockFileSystem({
            "kb1/index.md": index("Root1"),
            "kb2/index.md": index("Root2"),
            "kb2/parent/index.md": index("Parent"),
            "kb2/parent/child/index.md": index("Child"),
        })
        config = KBConfig(entries=[
            KBEntry("core", "kb1"),
            KBEntry("ios", "kb2"),
        ])
        multi = load_multi_kb(config, fs=fs)
        out = filter_topic(multi, "parent/child")
        assert out is not None
        kb_name, _ = out
        assert kb_name == "ios"

# ===================================================================
# filter_topic with @kb-name prefix
# ===================================================================

class TestFilterTopicAtKB:
    def _multi(self):
        """Two KBs with a shared topic name and unique topics."""
        fs = MockFileSystem({
            "kb1/index.md": index("Root1"),
            "kb1/shared/index.md": index("Shared Core", "Core version."),
            "kb1/only-core/index.md": index("Only Core"),
            "kb2/index.md": index("Root2"),
            "kb2/shared/index.md": index("Shared iOS", "iOS version."),
            "kb2/parent/index.md": index("Parent"),
            "kb2/parent/child/index.md": index("Child iOS"),
        })
        config = KBConfig(entries=[
            KBEntry("core", "kb1"),
            KBEntry("ios", "kb2"),
        ])
        return load_multi_kb(config, fs=fs)

    def test_at_kb_selects_correct_kb(self):
        multi = self._multi()
        out = filter_topic(multi, "@ios/shared")
        assert out is not None
        kb_name, d = out
        assert kb_name == "ios"
        assert d["index"]["name"] == "Shared iOS"

    def test_at_kb_skips_other_kb(self):
        multi = self._multi()
        out = filter_topic(multi, "@core/shared")
        assert out is not None
        kb_name, d = out
        assert kb_name == "core"
        assert d["index"]["name"] == "Shared Core"

    def test_at_kb_with_slash_path(self):
        multi = self._multi()
        out = filter_topic(multi, "@ios/parent/child")
        assert out is not None
        kb_name, d = out
        assert kb_name == "ios"
        assert d["index"]["name"] == "Child iOS"

    def test_at_kb_not_found_in_target(self):
        multi = self._multi()
        assert filter_topic(multi, "@ios/only-core") is None

    def test_at_kb_nonexistent_kb_name(self):
        multi = self._multi()
        assert filter_topic(multi, "@nope/shared") is None

    def test_at_kb_no_path_returns_none(self):
        multi = self._multi()
        assert filter_topic(multi, "@ios") is None

    def test_without_at_prefers_config_order(self):
        """Without @, shared topic returns first KB (config order)."""
        multi = self._multi()
        out = filter_topic(multi, "shared")
        assert out is not None
        kb_name, _ = out
        assert kb_name == "core"

# ===================================================================
# CLI --config flag
# ===================================================================

class TestConfigFlag:
    def test_auto_detect_default_config(self, tmp_path, monkeypatch):
        """No --config, no path — auto-detects .claude/knowledge-base/config.json."""
        monkeypatch.chdir(tmp_path)
        cfg_dir = tmp_path / ".claude" / "knowledge-base"
        cfg_dir.mkdir(parents=True)
        kb_dir = tmp_path / "knowledge" 
        kb_dir.mkdir(parents=True)
        (kb_dir / "index.md").write_text("---\nname: Root\n---\n")
        topic_dir = kb_dir / "my-topic"
        topic_dir.mkdir()
        (topic_dir / "index.md").write_text("---\nname: My Topic\ndescription: A topic.\n---\n")
        (cfg_dir / "config.json").write_text(json.dumps({
            "kb_roots": [{"name": "test", "path": "./knowledge"}]
        }))
        from kb_loader import main
        rc = main(["--list-topics"])
        assert rc == 0

    def test_explicit_config_path(self, tmp_path, monkeypatch):
        """--config points to a non-default location."""
        monkeypatch.chdir(tmp_path)
        kb_dir = tmp_path / "mydata" 
        kb_dir.mkdir(parents=True)
        (kb_dir / "index.md").write_text("---\nname: Root\n---\n")
        topic_dir = kb_dir / "topic"
        topic_dir.mkdir()
        (topic_dir / "index.md").write_text("---\nname: Topic\ndescription: Desc.\n---\n")
        custom_cfg = tmp_path / "custom.json"
        custom_cfg.write_text(json.dumps({
            "kb_roots": [{"name": "custom", "path": "./mydata"}]
        }))
        from kb_loader import main
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["--config", str(custom_cfg), "--list-topics"])
        assert rc == 0
        assert "@custom" in buf.getvalue()

    def test_missing_explicit_config_errors(self, tmp_path, monkeypatch):
        """--config to nonexistent file returns error."""
        monkeypatch.chdir(tmp_path)
        from kb_loader import main
        rc = main(["--config", "nonexistent.json", "--list-topics"])
        assert rc == 1

    def test_positional_path_overrides_config(self, tmp_path, monkeypatch):
        """Positional path uses single KB mode, ignores config."""
        monkeypatch.chdir(tmp_path)
        kb_dir = tmp_path / "mykb" 
        kb_dir.mkdir(parents=True)
        (kb_dir / "index.md").write_text("---\nname: Root\n---\n")
        topic_dir = kb_dir / "direct"
        topic_dir.mkdir()
        (topic_dir / "index.md").write_text("---\nname: Direct\ndescription: Loaded directly.\n---\n")
        from kb_loader import main
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main([str(tmp_path / "mykb"), "--list-topics"])
        assert rc == 0
        assert "direct" in buf.getvalue()

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
