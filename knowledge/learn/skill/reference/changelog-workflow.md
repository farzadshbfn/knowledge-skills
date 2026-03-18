# Changelog Workflow

## When

Every workflow run (article, topic, fix, compact) that changes any file under a knowledge folder MUST prepend an entry. No exceptions.

## Entry Format

```markdown
## YYYY-MM-DD HH:MM -- [type] Subject

1-2 sentences: what happened and why it matters (semantic, not mechanical).

- CREATE: `topic/new-note.md`
- UPDATE: `topic/existing-note.md`
- DELETE: `topic/removed-note.md`
```

**Fields**: Date/time via `date '+%Y-%m-%d %H:%M'`. Type: article|topic|fix|compact. Subject: 2-6 words. Change list: CREATE/UPDATE/DELETE with backtick paths relative to `<kb-root>`.

**Grouping** for many files: `CREATE: topic/note-a.md, note-b.md` or `UPDATE: 5 files across writing/skill/references/`.

## Placement

New entries at the top, directly after `# Changelog`. Newest first.

## What NOT to include

No frontmatter, no markdown links, no Source/Topics metadata, no template boilerplate.
