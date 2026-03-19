---
name: kb-compact
description: "Compacts KB directories — extracts legacy, unifies terminology, splits oversized notes, fixes indexes, reconciles with skill folders. Default: single directory. Use --deep for recursive bottom-up traversal."
argument-hint: "[--deep] [path/to/directory]"
hooks:
  PostToolUse:
    - matcher: "Write|Edit|Bash"
      hooks:
        - type: command
          command: "uv run ${CLAUDE_SKILL_DIR}/../../learn/skill/scripts/validate_kb.py --hook"
---

# /kb-compact

## 1. Configuration

Read KB config from `.claude/knowledge-base/config.json` (`kb_roots` array). Single KB: use its path. Multiple: AskUserQuestion which KB. No config: tell user "Run `/kb-bootstrap` to set up." and stop.

## 2. Input

Parse `$ARGS`:

- **`--deep`**: recursive bottom-up traversal. Without it: single directory only.
- **path**: optional, relative to project root or `<kb_root>`.
- No path: ask user. Offer "Compact whole KB" (warn: expensive, implies `--deep`) or specify subfolder.

## 3. Folder Structure

All restructuring follows [reference/folder-structure.md](reference/folder-structure.md) (canonical for clustering, unification, indexes, naming).

**Sibling unification first**: child folders grouped by semantically/lexicographically close names, run **before** other steps. 5+ siblings = medium sign; 8+ = high.

**Template:** [assets/index-note.md](assets/index-note.md)

## 4. Orchestration

- **Default**: Single [compacter agent](agents/compacter.md) for target directory.
- **`--deep`**: Follow [reference/deep-compaction.md](reference/deep-compaction.md) — tree analysis, level-based parallel [compacter agents](agents/compacter.md), bottom-up.

## 5. Changelog

Every run changing knowledge files MUST prepend to `<kb-root>/CHANGELOG.md` per `learning/skill/reference/changelog-workflow.md`.

## 6. User Approval

After all agents complete: present combined summary (files processed/moved/merged/split/created/deleted, terminology, legacy, indexes). AskUserQuestion: "Keep all", "Revert selectively", "Revert all". Selective: per-directory summaries, revert via `git checkout -- <paths>`.

## 7. Validation

After completing KB changes, run the validator to catch broken links, frontmatter issues, and structural errors:

```bash
uv run ${CLAUDE_SKILL_DIR}/../../learn/skill/scripts/validate_kb.py --quiet --json
```

Fix any reported errors before finishing.
