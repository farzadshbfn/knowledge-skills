# Folder Structure

How to organize folders, indexes, and notes in the KB.

## Contents
- [Hierarchical Clustering](#hierarchical-clustering)
- [Retroactive Sibling Unification](#retroactive-sibling-unification)
- [Skill Subfolders](#skill-subfolders)
- [Index Notes](#index-notes)
- [Forward-Only Application](#forward-only-application)

## Hierarchical Clustering

KB root has: `<category>s/` (notes in nested folders) and `CHANGELOG.md`.

Structure: `<category>/<topic>/<note>.md`
- Category folders group related topics (e.g., `animal/`)
- Topic folders hold notes (e.g., `animal/tiger/tiger-overview.md`)

**When to create folders**: Start with `<topic>/`. When 3+ topics share a category, create `<category>/<topic>` and nest topic folders inside.

**File naming**: lowercase, hyphen-separated, topic-prefixed when ambiguous (e.g., `tiger-overview.md`, `tcp-handshake.md`). 2-4 words.

## Retroactive Sibling Unification

After KB updates, check sibling folders for unification. Heuristic: 5+ siblings = medium signal, 8+ = high.

**Detection**: Group sibling folders by shared hyphen-delimited first segment. 3+ folders sharing a prefix = candidate. Skip if already unified. If an existing folder is itself a prefix of another (e.g., `api` vs `api-gateway`), suggest nesting inside it.

**If candidate found**: Ask user via AskUserQuestion with options: "Restructure now", "Skip", "Not applicable".

**If approved**:
1. `mkdir <parent>; mv` candidates, stripping shared prefix from folder names (`data-lake/` -> `data/lake/`)
2. Filenames inside stay as-is
3. Create category `index.md` ([template](../assets/index-note.md)), update parent `index.md`, update `.claude/skills/` symlinks
4. Fix links: inbound (`../<prefix>-<rest>/` -> `../<category>/<rest>/`), outbound (`../x/` -> `../../x/`), siblings (prefix stripped)
5. Run `validate_kb.py` to confirm zero broken links

## Skill Subfolders

Topics with actionable "how" content have a `skill/` subfolder. Must be **self-contained** (portable to repos without the KB).

```
<topic>/
  index.md          ← comprehensive: overview + skill map + related topics
  skill/            ← self-contained
    SKILL.md, reference/, agents/, assets/, scripts/
```

- Symlink from `.claude/skills/<name>` makes it discoverable
- All skills must be KB-backed (no standalone skills)
- **Only `index.md`** exists outside `skill/` in the concept folder
- `index.md` sections: `## Overview`, `## Skill` (link), `## Skill Contents` (full map), `## Related Topics`
- No files inside `skill/` may reference KB notes outside `skill/` (portability)

## Index Notes
<!-- CANONICAL: Index naming and location rules. Other files reference this section, not restate it. -->

Indexes follow the **proximity principle** — live in the same folder as concepts they organize.

- **Category index**: `<category>/index.md` — lists all topics
- **Topic index**: `<category>/<topic>/index.md` — links to notes in folder

**Sections**: `## Overview`, `## Core Concepts`, `## Related Topics`

**Lists vs Tables**: 1-2 items = bullet list. 3+ items = Markdown table:

```markdown
| Concept | Summary | Last updated |
|---------|---------|--------------|
| [Tiger Overview](tiger-overview.md) | High-level overview | 2026-03-05 |
```

Preserve existing tables when appending. Switch list to table when count exceeds 2.

**TOC requirement**: Notes exceeding **100 lines** need `## Contents` in first 10 body lines.

## Forward-Only Application

- Conventions apply to **new notes** by default. Existing notes are not moved automatically (exception: [Retroactive Sibling Unification](#retroactive-sibling-unification)).
- When editing existing notes: normalize frontmatter to `name` + `description`, update index links.
- To reorganize: `mv` files, run `validate_kb.py` to find broken links, fix them. Only rewrite content if content itself needs changing.

