# Deep Compaction

Recursive compaction via `--deep`. Spawns [compacter agents](../agents/compacter.md) bottom-up by depth level, one per directory.

## Contents
- [1. Resolve and Confirm](#1-resolve-and-confirm)
- [2. Analyze Tree](#2-analyze-tree)
- [3. Level-Based Spawning](#3-level-based-spawning)
- [4. Collect and Review](#4-collect-and-review)

## 1. Resolve and Confirm

1. Resolve path against `<kb_root>`.
2. If whole KB: warn expensive, AskUserQuestion ("Proceed?", "Subfolder instead", "Cancel").
3. If >50 markdown files: suggest narrowing.

## 2. Analyze Tree

Targets: KB root and descendants with topic notes. Skip `skill/`, `legacy/`, infrastructure dirs (`.venv`, `__pycache__`, `.pytest_cache`, `.obsidian`, `benchmark`, `node_modules`), and `CHANGELOG.md`.

1. List dirs under KB root recursively (include root itself).
2. Compute depth relative to KB root (level 0 = root).
3. Group by depth.

```
knowledge/              (KB root) -> L0
+-- topic-a/            -> L1 (skill/ inside: skip by compacter)
+-- category/           -> L1
    +-- topic-c/        -> L2
```

## 3. Level-Based Spawning

Process **bottom-up**, parallel within each level:

1. Spawn compacter agents for deepest level in parallel. Each gets `directory_path` + `kb_root`.
2. Wait for level to complete.
3. Move up one level, repeat. Agents see already-compacted subdirs.

**Optimization**: <3 markdown files and no subdirs -> compact inline (skip agent spawn).

## 4. Collect and Review

1. Aggregate all agent summaries.
2. Present combined summary (files processed, moved, merged, split, created, deleted, terminology, legacy, indexes).
3. AskUserQuestion: "Keep all", "Revert selectively", "Revert all".
4. Selective: per-directory summaries, revert via `git checkout -- <paths>`.

## Compacter Agent Behavior

See [compacter agent](../agents/compacter.md). Key behaviors: sibling unification first (child folders excluding `skill/`, `legacy/`, infra); skill-folder consolidation (only `index.md` outside `skill/`).
