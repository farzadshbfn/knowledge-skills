# Plugin Packaging Guide

## Contents
- [When to package](#when-to-package)
- [Naming and namespacing](#naming-and-namespacing)
- [Directory layout](#directory-layout)
- [KB-to-plugin migration](#kb-to-plugin-migration)
- [Cowork considerations](#cowork-considerations)
- [Packaging checklist](#packaging-checklist)

## When to Package

| Scenario | Action |
|----------|--------|
| Single skill, personal use | Stay standalone |
| Sharing across projects / marketplace | Plugin |
| Multiple related skills | Multi-skill plugin (namespaced) |
| Skills + MCP + hooks | Plugin (bundles all) |

## Naming and Namespacing

**Single skill**: plugin name = skill name, no namespace. `skills/my-tool/SKILL.md → /my-tool`

**Multi-skill**: derive plugin name from shared prefix. Skills become `/<plugin>:<action>`:
- `/topic-action1` → `/topic:action1`
- Find common hyphenated prefix → plugin name. Strip prefix → action name.

Edge cases: no common prefix → ask user. Mixed categories → separate plugins.

## Directory Layout

```
my-plugin/
├── .claude-plugin/plugin.json    ← manifest (name, description, version)
├── skills/<name>/SKILL.md        ← slash commands
├── agents/<agent>.md             ← subagents
├── hooks/hooks.json              ← event handlers
├── .mcp.json                     ← MCP servers
├── scripts/                      ← hook/skill scripts
└── settings.json                 ← plugin defaults
```

Rules: `skills/`, `agents/`, `hooks/` at plugin root (not inside `.claude-plugin/`). Use flat `skills/<name>/SKILL.md` layout (not KB-backed `skill/SKILL.md`).

### KB-Backed → Plugin Mapping

| KB-backed | Plugin |
|-----------|--------|
| `<topic>/skill/SKILL.md` | `skills/<action>/SKILL.md` |
| `<topic>/skill/reference/` | `skills/<action>/reference/` |
| `<topic>/skill/scripts/` | `scripts/` or `skills/<action>/scripts/` |
| `<topic>/skill/agents/` | `agents/` (shared) |
| Skill frontmatter `hooks:` | `hooks/hooks.json` (merged) |
| `.mcp.json` (project root) | `.mcp.json` (plugin root) |

## KB-to-Plugin Migration

1. Create `.claude-plugin/plugin.json` (use scaffold template)
2. Copy/flatten skills (resolve symlinks, KB-backed → flat layout)
3. Extract hooks from `settings.json` + skill frontmatter `hooks:` → `hooks/hooks.json` (deduplicate by matcher + command). Frontmatter hooks only fire while skill is active — promoting to plugin-level ensures consistency.
4. Move MCP configs, agents, update internal paths
5. Test: `claude --plugin-dir ./my-plugin`

For monorepo setups: use `git-subdir` in marketplace.json.

## Cowork Considerations

Same plugin format as Claude Code, with additions:

- **Connectors**: MCP servers show as "connectors" in GUI — use clear names in `.mcp.json`
- **GUI install**: No CLI-only setup steps — must work via `Customize` menu
- **Non-dev users**: Avoid manual CLI invocation. Prefer `user-invocable: false` for background ops
- **Marketplace**: `claude.com/plugins` unified — test both Code and Cowork
- **Memory**: Two-tier model — `CLAUDE.md` hot cache + `memory/` deep storage

## Packaging Checklist

- [ ] Tests excluded (`tests/`, `test_*.py` not shipped)
- [ ] Correct namespacing (single: no prefix, multi: `plugin:action`)
- [ ] `.claude-plugin/plugin.json` with name + description
- [ ] All paths relative to plugin root, scripts use `$CLAUDE_PLUGIN_ROOT`
- [ ] Hooks in `hooks/hooks.json` (including merged frontmatter hooks)
- [ ] MCP in `.mcp.json` at plugin root
- [ ] Tested with `claude --plugin-dir`
- [ ] Validated with `claude plugin validate .`
- [ ] Skill frontmatter descriptions quoted if they contain `: ` (YAML parse error otherwise)
- [ ] If Cowork: no CLI-only steps, clear connector names
