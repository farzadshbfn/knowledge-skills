---
name: kb-learn - Index
description: Index for the /kb-learn skill — a personal KB manager with three workflows (article, topic, fix) and an agent-assisted orchestration pipeline. Compaction moved to /kb-compact.
---

# kb-learn - Index

The `kb-learn` skill bootstraps and maintains a structured KB under `./knowledge/`. Invoked as `/kb-learn <mode> [input]`, it routes to one of three workflows. Compaction is handled by `/kb-compact`. Configuration lives at `.claude/knowledge-base/config.json`.

## Four Modes

| Mode | Input | Purpose |
|------|-------|---------|
| `article` | URL or pasted text | Extract claims, classify against KB (KNOWN/PARTIAL/NEW/EVOLVED), update |
| `topic` | Topic name | Research a topic, adapt depth to knowledge level (Novice/Familiar/Knowledgeable) |
| `fix` | Fix description | Find and correct errors in the KB, add correction callouts |
| `compact` | _(redirects to `/kb-compact`)_ | Normalize a directory — now handled by `/kb-compact` |

## Key Constraints

- Notes longer than **100 lines** must have `## Contents` in the first 10 lines of the body.
- Notes reaching **~500 lines** are candidates for compact/split.
- Max **5 tags** per note. No `created`/`updated` in frontmatter.
- File names: lowercase, hyphen-separated, topic-prefixed.
- Every workflow run that changes KB files MUST prepend a changelog entry.

## Workflows

Each mode follows a distinct but overlapping workflow. All workflows end with validation and a changelog entry. Shared procedures: claim classification (KNOWN/PARTIAL/NEW/EVOLVED), concept evolution (renamed/merged/split/superseded), and user approval before non-trivial writes.

| Workflow | Key steps |
|----------|-----------|
| **article** | Fetch, extract claims, classify, present diff, apply |
| **topic** | Load KB, assess level (Novice/Familiar/Knowledgeable), research, synthesize, apply |
| **fix** | Parse fix, scrutiny-mode KB read, locate error, apply correction callout |
| **compact** | Load all content, deduplicate with skill folder, extract legacy, unify terms, split oversized, fix indexes |

The skill uses an **orchestrator pattern** — SKILL.md spawns agents and chains their results. Agents never spawn other agents.

## KB Structure

The KB root is set in `.claude/knowledge-base/config.json` (`kb_root`, default `./knowledge/`). Contains topic folders (hierarchical notes) and `CHANGELOG.md` (rolling changelog at KB root).

- **Hierarchical clustering**: `<topic>/`. Category folders when 3+ topics share a broader theme. Forward-only — existing notes aren't moved automatically.
- **Three note types**: concept, index, legacy. All use `name` + `description` frontmatter only.
- **Progressive KB loading**: Multi-tier loading defined in `/kb-find`. See [finding-knowledge](../find/index.md).
- **Index proximity**: Indexes live next to the concepts they organize. Tables for 3+ items.
- **Changelog**: `CHANGELOG.md` at KB root. Newest entries first.

## Skill

Full procedures, agent definitions, and reference files: [`skill/SKILL.md`](skill/SKILL.md)

### Skill Contents

**Agents:**

| Agent | Model | Purpose |
|-------|-------|---------|
| [scouter](skill/agents/scouter.md) | haiku | KB discovery via progressive loading (supports `--challenge`) |
| [searcher](skill/agents/searcher.md) | sonnet | Web research — search, fetch, structure |
| [assessor](skill/agents/assessor.md) | opus | Evaluate claims against all evidence |

**References:**

| Reference | Purpose |
|-----------|---------|
| [article-workflow](skill/reference/article-workflow.md) | Article mode procedure |
| [topic-workflow](skill/reference/topic-workflow.md) | Topic mode procedure |
| [mistake-workflow](skill/reference/mistake-workflow.md) | Mistake/fix mode procedure |
| _deep-compaction_ | _(moved to `/kb-compact`)_ |
| [evolution-workflow](skill/reference/evolution-workflow.md) | Concept evolution handling |
| [changelog-workflow](skill/reference/changelog-workflow.md) | How to write CHANGELOG.md entries |
| [folder-structure](skill/reference/folder-structure.md) | KB folder conventions and templates |

## Related Topics

- [kb-find](../find/index.md) — Read-only KB discovery skill
- [kb-compact](../compact/index.md) — KB directory compaction skill (extracted from this skill)
