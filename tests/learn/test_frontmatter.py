"""Tests for frontmatter parsing and validation."""

from validate_kb import (
    ASSET, TOPIC, INDEX, PROJECT_AGENT, REFERENCE, SKILL, SKILL_AGENT, UNKNOWN,
    parse_frontmatter, validate_frontmatter,
)

class TestParseFrontmatter:
    def test_valid_topic_fm(self):
        fm, end = parse_frontmatter("---\nname: Test\ndescription: Desc\n---\nBody")
        assert fm == {"name": "Test", "description": "Desc"}
        assert end == 4

    def test_no_frontmatter(self):
        fm, end = parse_frontmatter("# Just a heading\n\nBody.")
        assert fm is None
        assert end == 0

    def test_unclosed_frontmatter(self):
        fm, end = parse_frontmatter("---\nname: Test\nNo closing delimiter")
        assert fm is None
        assert end == 0

    def test_boolean_fields(self):
        fm, _ = parse_frontmatter("---\nbackground: true\nactive: false\n---\n")
        assert fm["background"] is True
        assert fm["active"] is False

    def test_integer_fields(self):
        fm, _ = parse_frontmatter("---\nentries: 3\n---\n")
        assert fm["entries"] == 3
        assert isinstance(fm["entries"], int)

    def test_inline_list(self):
        fm, _ = parse_frontmatter("---\ntopics: [a, b, c]\n---\n")
        assert fm["topics"] == ["a", "b", "c"]

    def test_inline_list_quoted(self):
        fm, _ = parse_frontmatter('---\ntopics: ["path/a.md", "path/b.md"]\n---\n')
        assert fm["topics"] == ["path/a.md", "path/b.md"]

    def test_multiline_list(self):
        fm, _ = parse_frontmatter("---\nskills:\n  - kb-find\n  - kb-learn\n---\n")
        assert fm["skills"] == ["kb-find", "kb-learn"]

    def test_multiline_list_at_end(self):
        fm, _ = parse_frontmatter("---\nname: test\nskills:\n  - a\n  - b\n---\n")
        assert fm["name"] == "test"
        assert fm["skills"] == ["a", "b"]

    def test_string_with_special_chars(self):
        fm, _ = parse_frontmatter('---\nargument-hint: "<article|topic> [url]"\n---\n')
        assert fm["argument-hint"] == "<article|topic> [url]"

    def test_date_as_string(self):
        fm, _ = parse_frontmatter("---\ndate: 2026-03-10\n---\n")
        assert fm["date"] == "2026-03-10"
        assert isinstance(fm["date"], str)

    def test_empty_inline_list(self):
        fm, _ = parse_frontmatter("---\ntopics: []\n---\n")
        assert fm["topics"] == []

    def test_long_description(self):
        desc = "A " * 100 + "description."
        fm, _ = parse_frontmatter(f"---\nname: X\ndescription: {desc}\n---\n")
        assert fm["description"] == desc

    def test_tools_comma_separated_string(self):
        fm, _ = parse_frontmatter("---\ntools: Read, Glob, Grep\n---\n")
        assert fm["tools"] == "Read, Glob, Grep"

class TestValidateFrontmatter:
    def test_valid_note(self):
        fm = {"name": "Test", "description": "Desc"}
        assert validate_frontmatter(fm, TOPIC, "t/n.md") == []

    def test_topic_missing_name(self):
        fm = {"description": "Desc"}
        issues = validate_frontmatter(fm, TOPIC, "t/n.md")
        assert any(i.check == "missing_field" and "name" in i.message for i in issues)

    def test_topic_missing_description(self):
        fm = {"name": "Test"}
        issues = validate_frontmatter(fm, TOPIC, "t/n.md")
        assert any(i.check == "missing_field" and "description" in i.message for i in issues)

    def test_topic_empty_name(self):
        fm = {"name": "", "description": "Desc"}
        issues = validate_frontmatter(fm, TOPIC, "t/n.md")
        assert any(i.check == "empty_field" for i in issues)

    def test_topic_unexpected_field(self):
        fm = {"name": "Test", "description": "Desc", "tags": ["a"]}
        issues = validate_frontmatter(fm, TOPIC, "t/n.md")
        assert any(i.check == "unexpected_field" and "tags" in i.message for i in issues)

    def test_topic_no_frontmatter(self):
        issues = validate_frontmatter(None, TOPIC, "t/n.md")
        assert any(i.check == "frontmatter_missing" for i in issues)

    def test_valid_index(self):
        fm = {"name": "Idx", "description": "Index desc"}
        assert validate_frontmatter(fm, INDEX, "t/index.md") == []

    def test_valid_skill_with_all_optional(self):
        fm = {"name": "sk", "description": "Skill desc", "argument-hint": "<arg>", "user-invocable": True}
        assert validate_frontmatter(fm, SKILL, "t/skill/SKILL.md") == []

    def test_valid_skill_minimal(self):
        """Skills only require name and description — argument-hint is optional."""
        fm = {"name": "sk", "description": "Desc"}
        assert validate_frontmatter(fm, SKILL, "t/skill/SKILL.md") == []

    def test_skill_user_invocable_accepted(self):
        """user-invocable is a valid optional field for skills."""
        fm = {"name": "sk", "description": "Desc", "user-invocable": True}
        issues = validate_frontmatter(fm, SKILL, "t/skill/SKILL.md")
        assert not any(i.check == "unexpected_field" for i in issues)

    def test_skill_argument_hint_optional(self):
        """argument-hint is optional — no error when missing."""
        fm = {"name": "sk", "description": "Desc"}
        issues = validate_frontmatter(fm, SKILL, "t/skill/SKILL.md")
        assert not any(i.check == "missing_field" and "argument-hint" in i.message for i in issues)

    def test_valid_project_agent(self):
        fm = {"name": "ag", "description": "Agent desc", "tools": "Read", "model": "opus"}
        assert validate_frontmatter(fm, PROJECT_AGENT, ".claude/agents/ag.md") == []

    def test_project_agent_minimal(self):
        fm = {"name": "ag", "description": "Desc"}
        assert validate_frontmatter(fm, PROJECT_AGENT, ".claude/agents/ag.md") == []

    def test_project_agent_unknown_model(self):
        fm = {"name": "ag", "description": "Desc", "model": "gpt-4"}
        issues = validate_frontmatter(fm, PROJECT_AGENT, ".claude/agents/ag.md")
        assert any(i.check == "unknown_model" for i in issues)

    def test_project_agent_claude_prefix_model(self):
        fm = {"name": "ag", "description": "Desc", "model": "claude-opus"}
        assert validate_frontmatter(fm, PROJECT_AGENT, ".claude/agents/ag.md") == []

    def test_valid_skill_agent(self):
        fm = {"name": "sa", "description": "Desc", "tools": "Read", "model": "haiku", "background": True}
        assert validate_frontmatter(fm, SKILL_AGENT, "t/skill/agents/sa.md") == []

    def test_skill_agent_missing_tools(self):
        fm = {"name": "sa", "description": "Desc", "model": "haiku"}
        issues = validate_frontmatter(fm, SKILL_AGENT, "t/skill/agents/sa.md")
        assert any(i.check == "missing_field" and "tools" in i.message for i in issues)

    def test_skill_agent_missing_model(self):
        fm = {"name": "sa", "description": "Desc", "tools": "Read"}
        issues = validate_frontmatter(fm, SKILL_AGENT, "t/skill/agents/sa.md")
        assert any(i.check == "missing_field" and "model" in i.message for i in issues)

    def test_skill_agent_invalid_background(self):
        fm = {"name": "sa", "description": "D", "tools": "R", "model": "haiku", "background": "yes"}
        issues = validate_frontmatter(fm, SKILL_AGENT, "t/skill/agents/sa.md")
        assert any(i.check == "invalid_background" for i in issues)

    def test_skill_agent_invalid_skills(self):
        fm = {"name": "sa", "description": "D", "tools": "R", "model": "haiku", "skills": "not-a-list"}
        issues = validate_frontmatter(fm, SKILL_AGENT, "t/skill/agents/sa.md")
        assert any(i.check == "invalid_skills" for i in issues)

    # --- effort field ---

    def test_skill_valid_effort(self):
        for level in ("low", "medium", "high", "max"):
            fm = {"name": "sk", "description": "Desc", "effort": level}
            issues = validate_frontmatter(fm, SKILL, "t/skill/SKILL.md")
            assert not any(i.check == "invalid_effort" for i in issues), f"effort={level} should be valid"
            assert not any(i.check == "unexpected_field" and "effort" in i.message for i in issues)

    def test_skill_invalid_effort(self):
        fm = {"name": "sk", "description": "Desc", "effort": "extreme"}
        issues = validate_frontmatter(fm, SKILL, "t/skill/SKILL.md")
        assert any(i.check == "invalid_effort" for i in issues)

    def test_skill_effort_optional(self):
        fm = {"name": "sk", "description": "Desc"}
        issues = validate_frontmatter(fm, SKILL, "t/skill/SKILL.md")
        assert not any(i.check == "missing_field" and "effort" in i.message for i in issues)

    def test_project_agent_valid_effort(self):
        for level in ("low", "medium", "high", "max"):
            fm = {"name": "ag", "description": "Desc", "effort": level}
            issues = validate_frontmatter(fm, PROJECT_AGENT, ".claude/agents/ag.md")
            assert not any(i.check == "invalid_effort" for i in issues), f"effort={level} should be valid"
            assert not any(i.check == "unexpected_field" and "effort" in i.message for i in issues)

    def test_project_agent_invalid_effort(self):
        fm = {"name": "ag", "description": "Desc", "effort": "turbo"}
        issues = validate_frontmatter(fm, PROJECT_AGENT, ".claude/agents/ag.md")
        assert any(i.check == "invalid_effort" for i in issues)

    def test_skill_agent_valid_effort(self):
        for level in ("low", "medium", "high", "max"):
            fm = {"name": "sa", "description": "D", "tools": "R", "model": "haiku", "effort": level}
            issues = validate_frontmatter(fm, SKILL_AGENT, "t/skill/agents/sa.md")
            assert not any(i.check == "invalid_effort" for i in issues), f"effort={level} should be valid"
            assert not any(i.check == "unexpected_field" and "effort" in i.message for i in issues)

    def test_skill_agent_invalid_effort(self):
        fm = {"name": "sa", "description": "D", "tools": "R", "model": "haiku", "effort": "none"}
        issues = validate_frontmatter(fm, SKILL_AGENT, "t/skill/agents/sa.md")
        assert any(i.check == "invalid_effort" for i in issues)

    def test_reference_no_issues(self):
        assert validate_frontmatter(None, REFERENCE, "t/skill/reference/r.md") == []

    def test_asset_no_issues(self):
        assert validate_frontmatter({"name": "{{NAME}}"}, ASSET, "t/skill/assets/a.md") == []

    def test_unknown_no_issues(self):
        assert validate_frontmatter(None, UNKNOWN, "whatever.md") == []
