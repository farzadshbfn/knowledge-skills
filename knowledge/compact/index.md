---
name: kb-compact - Index
description: Index for the /kb-compact skill — compacts KB directories by extracting legacy, unifying terminology, splitting oversized notes, and fixing indexes.
---

# kb-compact - Index

The `kb-compact` skill normalizes and cleans up knowledge base directories. Invoked as `/kb-compact [path]`, it compacts the target directory. Use `--deep` to recursively compact subdirectories via bottom-up level-parallel agent traversal.

## Overview

Compaction keeps the KB maintainable as it grows. The skill handles:
- Extracting legacy/deprecated content into `legacy/` subfolders
- Unifying inconsistent terminology across notes
- Splitting oversized notes (~500+ lines) into focused pieces
- Fixing and rebuilding index notes
- Reconciling concept notes with skill folders (portability enforcement)
- Normalizing frontmatter and headers

## Skill

Full procedures, agent definitions, and reference files: [`skill/SKILL.md`](skill/SKILL.md)

### Skill Contents

**Agents:**

| Agent | Model | Purpose |
|-------|-------|---------|
| [compacter](skill/agents/compacter.md) | sonnet | Compact a single directory (full compaction logic) |

**References:**

| Reference | Purpose |
|-----------|---------|
| [deep-compaction](skill/reference/deep-compaction.md) | `--deep` orchestration — tree analysis, level-based parallel spawning, result collection |
| [folder-structure](skill/reference/folder-structure.md) | Canonical folder rules — hierarchical clustering, sibling unification, prefix stripping, index placement |

## Related Topics

- [kb-learn](../learn/index.md) — KB management skill (article, topic, fix workflows)
