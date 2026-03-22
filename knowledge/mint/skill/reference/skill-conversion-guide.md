# Skill Conversion Guide

## Contents
- [Content assessment](#content-assessment)
- [Scaffold and structure](#scaffold-and-structure)
- [Agent decomposition](#agent-decomposition)
- [Portability check](#portability-check)
- [Finalize](#finalize)
- [Checklist](#checklist)

## Content Assessment

Use `/kb-find` to load all notes. Classify:

| Content Type | Destination |
|-------------|-------------|
| What/where/when | `index.md` (slim) |
| How/procedure/workflow | `skill/SKILL.md` or `skill/reference/` |
| Reference data | `skill/reference/` |
| Templates | `skill/assets/` |
| Automatable operations | `skill/scripts/` |

## Scaffold and Structure

Use `../assets/skill-scaffold/SKILL.md.template`. Create `skill/SKILL.md` (routing + pointers) and slim `index.md` to concept summary.

Token efficiency rules:
- **SKILL.md < 500 lines** — routing table, not a monolith
- **Reference files independent** — each loadable alone, no cross-references
- **One-level-deep** — SKILL.md → reference (never reference → reference)
- **Scripts over inline logic** — `uv run script.py` ~50 tokens vs ~300+ generated
- **Agents for bulk work** — haiku/discovery, sonnet/analysis, opus/judgment

Scripts: PEP 723 inline metadata, pure functions, CLI entry point. Add when doing repeated extraction, validation, or file ops.

## Agent Decomposition

Add `skill/agents/` when needed for parallel queries, isolating high-volume output, or cheaper model delegation. Each agent is self-contained (no nesting).

Frontmatter: `name`, `description`, `tools`, `model` (haiku|sonnet|opus).

## Portability Check

Scan `skill/` for links outside the folder (break on distribution):
- Content can move in → move to `skill/reference/`
- References another skill → replace with skill invocation mention
- Back-links to parent `../index.md` → harmless, leave
- Other external → inline if needed, remove if not

## Finalize

1. Symlink: `ln -s ../../knowledge/<topic>/skill .claude/skills/<name>`
2. Skill exclusivity: only `index.md` outside `skill/` — move other `.md` files in
3. Validate: `uv run ${CLAUDE_SKILL_DIR}/../kb-learn/scripts/validate_kb.py --quiet --json`
4. Prepend CHANGELOG.md (`[maintenance]`)
5. If from monitoring: return control for memory update

## Checklist

- [ ] All "how" content in skill/, index.md slim
- [ ] SKILL.md < 500 lines, references independent
- [ ] No skill file links to KB-level notes outside skill/
- [ ] Symlink in .claude/skills/, no stray .md at concept level
- [ ] validate_kb.py passes, CHANGELOG.md updated
