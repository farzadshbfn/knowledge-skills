# Article Learning Workflow

Process an article (URL or pasted text), extract claims, compare against KB, and update with new learnings.

## Contents
- [Input](#input)
- [Steps](#steps)

## Input

`$ARGS` = URL to an article, or pasted article text

## Steps

### 1. Fetch the Article

- **URL**: Follow [fetch-content.md](fetch-content.md) to fetch and cache. If fetch fails, ask user to paste text.
- **Text**: Use directly as article content.
- **Neither**: Ask user for URL or pasted text.

### 2. Extract Claims

Separate content into: **factual claims** (verifiable statements), **definitions** (new terms/taxonomies), **author opinions** (subjective takes, labeled clearly). Note each claim's paraphrase, source section, and category.

### 3. Load KB

Spawn a [scouter](../agents/scouter.md) in normal mode with extracted claims/key terms (SKILL.md §3). For many claims or expected deep assessment, spawn two scouters (normal + challenge) upfront.

### 4. Classify Each Claim

- **KNOWN**: Already in KB — cite with link
- **PARTIAL**: Extends existing knowledge
- **NEW**: Not covered in KB
- **EVOLVED**: Same concept, different name/version — flag for [evolution-workflow.md](evolution-workflow.md)

Author opinions tagged separately. After classification, compare terminology against KB — newer terms for existing concepts = EVOLVED, not PARTIAL.

### 4a. Deep Assessment (Optional)

For **5+ non-KNOWN claims**: if only normal scouter was spawned, add a challenge-mode scouter. Then spawn [assessor](../agents/assessor.md) with claims + KB findings. Assessor produces per-claim verdicts. Skip for few claims or small KB.

### 5. Present the Diff

Show structured comparison: already known (with links), partially covered (what's new), new information, author opinions (unverified), evolution detected (old→new term), and proposed KB changes (CREATE/UPDATE/EVOLVE with paths). Include source URL, date, and claim counts.

### 6. Await Approval

Use SKILL.md shared approval procedure. User may approve all, approve selectively, reject with feedback, or skip opinions.

### 7. Apply Changes

Check for `skill/` subfolder first (SKILL.md §4 step 0a) — route "how" content to skill, keep concept notes lightweight.

1. **New notes**: Use `assets/topic-note.md`. Set `name`/`description`. Add cross-references. Add `## References` with article URL. Add `## Contents` if >100 lines.
2. **Updated notes**: Add sections/details. Keep frontmatter accurate. Add links and references. Add `## Contents` if >100 lines and missing.
3. **Evolved concepts**: Follow [evolution-workflow.md](evolution-workflow.md) for callouts, cross-links, legacy notes.
4. **Index notes**: Update/create indexes. Use table format when 3+ items (see [folder-structure.md](folder-structure.md)).
