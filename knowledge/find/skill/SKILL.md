---
name: kb-find
description: Read-only KB discovery with progressive 4-tier loading and --challenge mode for counter-evidence.
argument-hint: "<query> [--challenge]"
effort: medium
---

# /kb-find

Progressive 4-tier KB discovery. **Read-only.**

## Constraints
- **NEVER** Read `index.md` or `config.json` — kb_loader handles these; config auto-detects.
- Combine reasoning + tool calls per turn. Batch parallel Bash/Read calls.
- Only Read individual concept `.md` files (Tier 2/3/4).
- **Global KBs** (shown with `[read-only]` badge in topic listing) are searchable but not writable. Treat them identically for discovery.

## 1. Input Parsing

Parse query from `$0`, strip flags. Two modes:

- **Default**: find concept notes matching query keywords.
- **`--challenge`**: find content that **contradicts or complicates** the query. Score by contradiction potential. Include adjacent topics. Read 1-2 extra notes in Tier 3/4. Skip KB meta-topics unless query is about them.

## 2. Tier 1 — KB Loader Queries

`KB_LOADER="${CLAUDE_SKILL_DIR}/scripts/kb_loader.py"`

1. `$KB_LOADER --list-topics` — tree by `@kb-name` with `[skill]` tags.
2. Pick relevant topics. Slash paths (`compact`) or `@kb-name/path`. Challenge: also contradicting topics.
3. `$KB_LOADER --topic <path>` per topic. All calls in one turn.
4. Build topic map: `{topic_name, notes[], children[], has_skill}`.

`--topic` returns JSON (names/descriptions) for Tier 2 scoring. Empty list → report and stop.

## 3. Tier 2 — Frontmatter Scan

**Skip** if Tier 1 name+description clearly shows relevance → Tier 3/4. Only scan ambiguous notes.

1. Read first **15 lines**. Extract name, description, summary.
2. Score relevance; promote if warranted. Cap 2-3 candidates.

## 4. Tier 3 — TOC Section Read

**Skip to Tier 4** if no TOC or note is <100 lines.

1. Read first **30 lines** (frontmatter + TOC). If already read 15, use `offset=16, limit=15`.
2. Read relevant sections **±1 adjacent**.
3. Follow relevant **markdown links** → Tier 2. Cross-KB links (`@kb-name/path`) → `--topic @kb-name/topic`.
4. Follow **soft references** (lines starting with `see:` followed by `@kb/topic`) → `--topic @kb/topic`. These are semantic hints to global KBs.

## 5. Tier 4 — Full Read

1. Full read when no TOC or Tier 3 insufficient. Use `offset` to skip prior lines.
2. Cap **500 lines/note**; note truncation. **>10 notes** → ask user to narrow.
3. Follow relevant links → Tier 2.

## 6. Output

Return: `## Topic Map` (paths), `## Relevant Concept Notes` (path + title + content, label concept vs skill), `## Notes` (caveats).

**Challenge mode** output: `## Topic Map`, `## Counter-Evidence` (path, strength, type, excerpt), `## Summary` (1-3 sentences), `## Notes`.
