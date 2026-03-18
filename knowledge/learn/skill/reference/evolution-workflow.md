# Evolution and Legacy Workflow

How to detect concept evolution in the KB and document old/legacy patterns. Called from article, topic, and fix workflows when something is classified as **EVOLVED** or identified as deprecated/superseded.

## Contents
- [1. What Counts as Evolution](#1-what-counts-as-evolution)
- [2. Detecting Evolution](#2-detecting-evolution)
- [3. Applying Changes](#3-applying-changes)
- [4. Old Patterns in Main Note](#4-old-patterns-in-main-note)
- [5. Legacy Notes](#5-legacy-notes)
- [6. Interaction with Workflows](#6-interaction-with-workflows)

## 1. What Counts as Evolution

The KB has content about a concept but under outdated framing:
- **Renamed**: different terminology (e.g., "commands" → "skills")
- **Merged**: two KB concepts unified into one
- **Split**: one KB concept divided into multiple
- **Superseded**: replaced by a fundamentally different approach/version

## 2. Detecting Evolution

After the main classification step (KNOWN/PARTIAL/NEW/EVOLVED):

1. When a finding feels like "same idea, different name/version", prefer **EVOLVED** over **PARTIAL**
2. Compare terminology: naming changes, version markers (v1 vs v2), framing shifts
3. Map old ↔ new concepts (existing KB notes vs new concept)
4. Decide type: renamed/merged/split/superseded
5. List evolution findings prominently (above "New information") — they're corrections to existing knowledge

## 3. Applying Changes

For each evolved concept:

1. **Evolution callout** at top of affected note's Overview:
   ```markdown
   > [!evolution] {{DATE}}
   > Previously documented as "X". This has been [renamed to/merged into/superseded by] "Y" [because Z]. See [New Note](../path/to/new-note.md).
   ```
2. **Cross-links**: bidirectional links between old and new notes. Update indexes to link to new note.
3. **Metadata**: update `description` to mention older framing; update `name` if renamed
4. **No silent rewrites**: add callouts and cross-links rather than erasing history

## 4. Old Patterns in Main Note

When evolution reveals a deprecated pattern, add an `Old patterns` section at the same heading level as the current scope, near the end:

```markdown
#### Old patterns

<details>
<summary>Legacy v1 API (deprecated 2025-08)</summary>

The v1 API used: `api.example.com/v1/messages` — no longer supported.
</details>
```

Keep it lightweight. If the old approach needs long documentation (code listings, multi-step workflows, or would push note toward 500 lines), use a legacy note instead.

## 5. Legacy Notes

For detailed legacy documentation, create a dedicated legacy note in `legacy/` inside the concept folder.

- Location: `<topic>/legacy/<topic>-<feature>-legacy-v1.md`
- Template: [assets/legacy-note.md](../assets/legacy-note.md)
- Frontmatter: `name` (append " (legacy)"), `description` (mention replacement + brief summary)
- Body: `# {Title} (legacy)`, summary, disclaimer, then Overview/Why replaced/Details/Migration/References
- **From main note**: link in `## Old patterns` section
- **From legacy note**: link back to main note in Overview or `## Superseded by`

## 6. Interaction with Workflows

- **Article**: When article reveals renamed APIs or superseded methods → classify as EVOLVED → apply evolution callouts + decide on Old patterns vs legacy note
- **Topic**: When research discovers outdated KB terminology → treat as evolution → update notes
- **Fix**: If reported error is actually outdated terminology/version → use evolution workflow instead of just correction callout
