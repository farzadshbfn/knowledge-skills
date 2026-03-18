---
name: kb-mint
description: Mints skills from KB topics, packages skills into plugins, and prepares them for Cowork. Use when asked to create a skill from KB content, convert to a plugin, package for distribution, or make something cowork-ready. Also triggers on `convert this to a skill`, `package as plugin`, `mint a skill`, or `make this a plugin`.
argument-hint: "[--skill <topic-path> | --plugin <skills...> | --cowork <skills...>]"
---

# /kb-mint — KB-to-Skill-to-Plugin Pipeline

## 1. Routing

Parse `$0` to determine mode:

- `--skill <topic-path>` → Section 2
- `--plugin <skills...>` → Section 3
- `--cowork <skills...>` → Section 4
- Otherwise → show: `/kb-mint --skill|--plugin|--cowork <args>`

## 2. Skill Conversion (`--skill`)

Convert a KB concept topic into a KB-backed skill.

1. **Load**: Use `/kb-find` to discover all notes in the target topic
2. **Assess**: Classify per [reference/skill-conversion-guide.md](reference/skill-conversion-guide.md) (what/where/when → `index.md`, how → `skill/`, data → `reference/`, templates → `assets/`, automation → `scripts/`)
3. **Author**: If `/skill-creator` is available in the environment, delegate skill creation to it. Otherwise, follow [reference/skill-authoring-guide.md](reference/skill-authoring-guide.md) for description writing, workflow patterns, token efficiency
4. **Present plan** → ask for approval
5. **Execute**: Scaffold from [assets/skill-scaffold/SKILL.md.template](assets/skill-scaffold/SKILL.md.template), slim `index.md`, create symlink (`ln -s ../../knowledge/<topic>/skill .claude/skills/<name>`), validate (`uv run ${CLAUDE_SKILL_DIR}/../../learn/skill/scripts/validate_kb.py --quiet --json`)
6. **Records**: Prepend `knowledge/CHANGELOG.md` (`[maintenance]`). If from monitoring, return control.

## 3. Plugin Packaging (`--plugin`)

1. **Resolve skills** via `.claude/skills/` symlinks or direct paths
2. **Name plugin**: Derive from common prefix per [reference/plugin-packaging-guide.md](reference/plugin-packaging-guide.md). Single skill → name = skill name. Multiple → `plugin:action` namespace. Confirm with user.
3. **Present plan**: name, namespace, layout, hooks/MCP/agents extraction
4. **Execute**: Create plugin dir, generate `plugin.json` from [assets/plugin-scaffold/plugin.json.template](assets/plugin-scaffold/plugin.json.template), copy skills, extract hooks to `hooks/hooks.json` (merge skill frontmatter `hooks:` — deduplicate by matcher + command), extract MCP to `.mcp.json`, create agents
5. **Finalize**: Validate, present for review

## 4. Cowork Packaging (`--cowork`)

Run Section 3 first, then add Cowork-specific considerations per [reference/plugin-packaging-guide.md § Cowork](reference/plugin-packaging-guide.md): connectors (MCP as GUI connectors), GUI installation (no CLI-only steps), non-dev users (`user-invocable: false`), marketplace labels. Present additions for approval.

## 5. Scripts and Testing

- **Scripts/MCP**: See [reference/uv-scripting-guide.md](reference/uv-scripting-guide.md)
- **Testing**: See [reference/testing-guide.md](reference/testing-guide.md)
- Run tests: `uv run scripts/tests/run_tests.py -q`
