"""Pytest fixtures for validate_kb tests."""

import pytest
from validate_kb import MockFileSystem
from learn_helpers import (
    asset,
    note,
    index,
    project_agent,
    reference,
    skill,
    skill_agent,
)

@pytest.fixture
def valid_kb() -> MockFileSystem:
    """A minimal valid knowledge base with all file types."""
    return MockFileSystem({
        # Root index — links to both topic subfolders
        "kb/index.md": (
            index("Topics - Index", "Root index.")
            + "\n- [Topic A](topic-a/index.md)\n- [Topic B](topic-b/index.md)\n"
        ),
        # Topic A with index that links to skill subfolder
        "kb/topic-a/index.md": (
            index("Topic A - Index", "Index for topic A.")
            + "\n- [Skill](skill/SKILL.md)\n"
        ),
        # Topic B (no skill — topic notes allowed)
        "kb/topic-b/index.md": (
            index("Topic B - Index", "Index for topic B.")
            + "\n## Core Topics\n\n- [Note One](note-one.md) — first note\n"
        ),
        "kb/topic-b/note-one.md": note("Note One", "First note."),
        # Skill — links to agents, assets, reference subdirs
        "kb/topic-a/skill/SKILL.md": (
            skill("topic-a", "Topic A skill.", "<arg>")
            + "\n- [Scout](agents/scout.md)\n- [Template](assets/template.md)\n"
            + "- [Workflow](reference/workflow.md)\n"
        ),
        "kb/topic-a/skill/agents/scout.md": skill_agent(
            "scout", "Scout agent.", "Read, Glob", "haiku", True, ["kb-find"],
        ),
        "kb/topic-a/skill/assets/template.md": asset(),
        "kb/topic-a/skill/reference/workflow.md": reference(),
        # Project agent (outside KB root)
        ".claude/agents/sync.md": project_agent(
            "sync", "Sync agent.", "Read, Glob, Grep", "opus", ["topic-a"],
        ),
    })

@pytest.fixture
def broken_kb() -> MockFileSystem:
    """A knowledge base with various known issues for testing."""
    long_content = "\n".join([f"Line {i}" for i in range(150)])

    return MockFileSystem({
        # Root index
        "kb/index.md": index("Topics - Index", "Root index."),

        # --- Frontmatter issues ---
        "kb/topic-a/index.md":
            "# No Frontmatter Index\n\n- [bad-fm](bad-fm.md)\n- [orphan-note](../topic-b/orphan.md)\n",
        "kb/topic-a/bad-fm.md":
            "---\nname: Bad FM\n---\n\n# Bad FM\n\nMissing description.\n",
        "kb/topic-a/skill/SKILL.md":
            "---\nname: topic-a\ndescription: A skill.\n---\n\nBody.\n",
        "kb/topic-a/skill/agents/bad-agent.md":
            "---\nname: bad\ndescription: Bad agent.\ntools: Read\nmodel: gpt-4\nbackground: yes\n---\n\nBody.\n",
        "kb/topic-a/skill/reference/bad-scope.md":
            "See [index](../../index.md) and [missing](nonexistent.md) for context.\n",
        "kb/topic-b/orphan.md":
            "---\nname: Orphan\ndescription: An orphan note.\ntags: [test]\n---\n\n# Orphan\n",

        # --- Structural issues ---
        "kb/topic-b/index.md":
            "---\nname: Topic B - Index\ndescription: Topic B.\n---\n\n"
            "# Topic B\n\n- [Missing](nonexistent.md)\n- [Orphan](orphan.md)\n",
        "kb/topic-b/wiki-note.md":
            "---\nname: Wiki Note\ndescription: Has wikilinks.\n---\n\n"
            "# Wiki\n\nSee [[some-page]] for details.\n",
        "kb/topic-b/big-note.md":
            "---\nname: Big Note\ndescription: Oversized.\n---\n\n# Big\n\n"
            + "\n".join(f"Line {i}" for i in range(510)),
        "kb/topic-b/long-no-toc.md":
            "---\nname: Long No TOC\ndescription: Long without TOC.\n---\n\n"
            "# Long Note\n\n" + long_content,

        # --- Code block edge cases ---
        "kb/topic-b/code-note.md":
            "---\nname: Code Note\ndescription: Has code blocks.\n---\n\n"
            "# Code\n\n```markdown\n[link](fake.md)\n[[wikilink]]\n```\n\n"
            "And `[inline](also-fake.md)` code.\n\n"
            "But [real-link](../topic-a/index.md) works.\n",

        # Project agent (outside KB)
        ".claude/agents/good-agent.md": project_agent("good", "Good agent."),
    })
