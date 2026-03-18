---
name: kb-find - Index
description: Index for notes about the `/kb-find` Claude Code skill — a read-only KB discovery tool using progressive loading.
---

# kb-find - Index

## Overview

The `kb-find` skill discovers relevant knowledge base content without modifying any files. It was extracted from the `/kb-learn` skill's embedded progressive loading procedure so that any skill or agent can discover KB content without depending on the full learning-knowledge skill.

The KB can grow large. Reading every note on every invocation wastes tokens and context window. `/kb-find` solves this with progressive 4-tier loading — each tier is progressively more expensive but more targeted. Guardrails: 500 lines max per note, 10 notes max before narrowing scope.

Strictly read-only — never creates, edits, or deletes files.

## Usage Patterns

- **Standalone**: `/kb-find "distributed systems"` — returns relevant concept notes and topic map.
- **By skills**: `/kb-learn` and `/writing-article` both call it for KB discovery. Platform writing rules are read from skill-owned reference files, not via `/kb-find`.
- **By agents**: The scouter agent uses kb-find via the `skills: [kb-find]` frontmatter field, invoking it with and without `--challenge` for evidence evaluation. Writer agents receive material in their invocation message instead.

## Key Concepts

| Concept | Summary |
|---------|---------|
| Progressive loading | 4-tier loading from cheap metadata (kb_loader) to frontmatter scan to TOC section read to full read |
| Challenge mode | `--challenge` flag switches the lens from supporting to counter-evidence, widening into adjacent topics |

For the full procedural steps (tiers, output format), see [`skill/SKILL.md`](skill/SKILL.md).

## Related Topics

- [kb-learn](../learn/index.md) — The KB management skill this was extracted from (includes KB structure conventions)
