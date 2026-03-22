# Topic Learning Workflow

Assess the user's knowledge level, research authoritative sources, and add new learnings to the KB.

## Contents
- [Input](#input)
- [Steps](#steps)

## Input

`$ARGS` = topic name or phrase (e.g., "why circadian rhythm matters for sleep")

## Steps

### 1. Load KB for the Topic

Spawn a [scouter](../agents/scouter.md) in normal mode with the topic name (see SKILL.md §3).

### 2. Assess Knowledge Level

Based on KB content, classify the user's level:
- **Novice**: No notes on this topic or prerequisites
- **Familiar**: Some related notes exist, partial coverage
- **Knowledgeable**: Notes exist; seeking deeper understanding, edge cases, advanced aspects

### 3. Check Prerequisites

If **Novice**: Identify prerequisite concepts, check if they exist in KB, flag missing ones. Ask: learn prerequisites first, or include alongside?

### 4. Research

Use **WebSearch** for 3-5 high-quality sources (official docs, guides, papers, expert blogs). Skip AI-generated, outdated, or redundant sources.

**Agent option**: Use [searcher](../agents/searcher.md) for high-volume research (runs in parallel with scouter — see SKILL.md §2a).

**Depth by URL count**:
- **1-2 URLs**: Auto-fetch and analyze using [fetch-content.md](fetch-content.md)
- **3+ URLs**: Ask user preference — synthesize (default, faster) or deep-dive (fetch all, more thorough)

### 5. Synthesize

Adapt to level: **Novice** → fundamentals, define terms, analogies. **Familiar** → skip known basics, connect to existing notes. **Knowledgeable** → advanced aspects, edge cases, pitfalls.

### 6. Classify Findings

For each finding: **KNOWN** (cite with link), **PARTIAL** (extends existing), **NEW** (not in KB), **EVOLVED** (same concept, different name/version — see [evolution-workflow.md](evolution-workflow.md)).

### 6a. Detect Concept Evolution

After classification, check for evolution patterns per [evolution-workflow.md](evolution-workflow.md).

### 6b. Deep Assessment

For **any non-KNOWN findings**: spawn challenge-mode scouter with classified findings and KB evidence.

### 6c. Challenger

Spawn [challenger](../agents/challenger.md) with non-KNOWN claims from step 6, scouter KB context, and searcher sources. The challenger actively searches the web for counter-evidence, alternative explanations, and edge cases against each claim.

### 6d. Assessor

Spawn [assessor](../agents/assessor.md) with classified findings, KB evidence, web findings, **and challenger counter-evidence**. Assessor produces per-claim verdicts incorporating the challenger's challenges.

### 7. Present Findings

Show structured overview: current level, what's already known (with links), prerequisites (if applicable), evolution detected, new information (adapted to level), sources consulted, and proposed KB changes (CREATE/UPDATE/EVOLVE with paths). Separate `<conf:low>` claims visually — prefix with ⚠ and note they will be excluded by default.

### 8. Approval

Non-trivial changes: use SKILL.md shared approval procedure. Minor additions: proceed but mention.

### 9. Apply Changes

Check for `skill/` subfolder first (SKILL.md §4 step 0a) — route "how" content to skill, keep concept notes lightweight.

1. **New notes**: Use `assets/topic-note.md`. Set `name`/`description` in frontmatter. Add cross-reference links. Add `## References` with URLs. Add `## Contents` if >100 lines. Append the assessor's confidence tag (`<conf:high>`, `<conf:medium>`, `<conf:low>`) inline after each claim.
2. **Updated notes**: Add sections/details. Keep frontmatter accurate. Add links and references. Add `## Contents` if >100 lines and missing. Append confidence tags to new claims. Preserve existing tags on unchanged claims.
3. **Evolved concepts**: Follow [evolution-workflow.md](evolution-workflow.md) for callouts, cross-links, legacy notes.
4. **Index notes**: Update/create indexes. Add links under appropriate section. Use table format when section has 3+ items (see [folder-structure.md](folder-structure.md)).
