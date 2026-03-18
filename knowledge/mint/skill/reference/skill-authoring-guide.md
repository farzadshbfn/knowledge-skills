# Skill Authoring Guide

Guiding principle: Claude is already smart — only add context it doesn't already have. Every token competes with conversation history.

## Contents
- [Core principles](#core-principles)
- [Description writing](#description-writing)
- [Degrees of freedom](#degrees-of-freedom)
- [Workflow patterns](#workflow-patterns)
- [Content guidelines](#content-guidelines)
- [Development process](#development-process)
- [Anti-patterns](#anti-patterns)
- [Pre-publish checklist](#pre-publish-checklist)

## Core Principles

- **Only add what Claude doesn't know** — domain-specific or context-specific knowledge only
- **Test with all target models** — Haiku needs more guidance, Opus needs less
- **Separate logic from `__main__`** — testable script layout
- **Handle errors in scripts** — don't punt to Claude
- **Document constants** — no "voodoo constants"
- **One category per skill** — best skills fit cleanly into one skill category (see `claude/skills/skill-categories.md`); straddling multiple is a sign to split or simplify

## Description Writing

- **Third person**: "Processes Excel files..." not "I can help you..."
- **Include trigger context**: "Use when working with PDF files or when the user mentions PDFs..."
- **Be specific**: Key terms that signal when to activate from 100+ skills
- **Avoid `"` in descriptions**: Use backticks for trigger phrases. If description contains `: `, wrap the whole value in single quotes: `description: 'Does X. Modes: (1) foo.'`
- Bad: `"Helps with documents"`, `"Processes data"`

## Degrees of Freedom

Match specificity to task fragility:

| Level | When | Format |
|-------|------|--------|
| **High** | Multiple valid approaches | Plain text |
| **Medium** | Preferred pattern, some variation OK | Pseudocode/template |
| **Low** | Fragile/error-prone, exact sequence | Scripts, exact commands |

Narrow bridge with cliffs → exact instructions. Open field → general direction.

## Workflow Patterns

**Checklist** — for multi-step tasks, provide a checklist Claude copies and tracks. Prevents skipping validation.

**Feedback loop** — run validator → fix errors → repeat. Only proceed when validation passes.

**Template** — strict: "ALWAYS use this exact template". Flexible: "sensible default, use your judgment".

**Examples (I/O pairs)** — concrete input/output pairs when output quality depends on examples.

**Conditional** — guide through decision points: "Creating new? → Creation workflow. Editing? → Editing workflow."

> Large workflows → push into separate files, tell Claude to read the appropriate one.

## Content Guidelines

- **Deprecated content**: Use `<details>` "Old patterns" blocks, never date-based conditions
- **Consistent terminology**: Pick one term, use it everywhere (not "API endpoint"/"URL"/"route")

## Development Process

### Evaluation-Driven Development
1. Run Claude on tasks without a Skill, document failures
2. Create 3+ evaluations covering identified gaps
3. Establish baseline, write minimal instructions to pass
4. Iterate: evaluate → refine → re-evaluate

### Claude A/B Refinement
- **Claude A** designs/refines the skill based on task experience
- **Claude B** (fresh instance) tests it on related use cases
- Iterate based on B's behavior failures

### Plan-Validate-Execute
For batch/destructive operations: Claude creates plan file → script validates → execute only after validation passes.

## Gotchas Section

The highest-signal content in any skill is the **Gotchas** section. Build it from common failure points Claude hits when using the skill. Update it over time as new edge cases surface. A growing gotchas section is a sign of a healthy, battle-tested skill.

## Setup Pattern

Some skills need user-specific configuration (e.g., which Slack channel, which environment). Store setup info in a `config.json` in the skill directory. If config is missing, prompt the user — use the `AskUserQuestion` tool for structured, multiple-choice questions.

## On-Demand Hooks

Skills can include hooks that activate only when the skill is called and last for the session duration. Use for opinionated hooks that shouldn't run always but are powerful sometimes. Examples: `/careful` (blocks `rm -rf`, `DROP TABLE`, force-push via PreToolUse matcher), `/freeze` (blocks Edit/Write outside a specific directory during debugging).

## Memory & Data Storage

Skills can store data within themselves — append-only text logs, JSON files, or even SQLite databases. Example: a standup skill keeping a `standups.log` so Claude reads its own history and reports what changed.

**Important:** Data stored in the skill directory may be deleted on skill upgrade. Use `${CLAUDE_PLUGIN_DATA}` (stable per-plugin folder) for persistent storage.

## Anti-Patterns

- Windows-style paths (use forward slashes)
- Too many options (provide default + escape hatch)
- Assuming tools installed (list deps explicitly)
- Deeply nested references (keep one level deep from SKILL.md)
- Oversized SKILL.md (>500 lines → split into reference files)
- **Code blocks for standard patterns** — Claude knows pytest, mock, loops, common libs. Name the pattern, don't show the code. Only use code blocks for non-obvious or project-specific syntax.
- **Verbose agent prompts** — state constraints and output format only. Skip obvious steps — agents are Claude too.
- **Inline output templates** — describe structure in prose ("return JSON with fields: x, y, z"), don't show full code-fenced examples.

## Pre-Publish Checklist

- [ ] Description: specific, third-person, trigger context
- [ ] SKILL.md < 500 lines
- [ ] No time-sensitive info (or in "old patterns")
- [ ] Consistent terminology, one-level-deep references
- [ ] Reference files >100 lines have TOC
- [ ] Scripts handle errors, no unexplained constants
- [ ] 3+ evaluations, tested with Haiku/Sonnet/Opus
