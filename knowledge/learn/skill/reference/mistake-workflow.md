# Fix Workflow

Correct errors in the knowledge base.

## Input

`$ARGS` = description of what to fix (e.g., "melatonin is triggered by darkness, not blue light")

## Steps

### 1. Parse the Fix

Extract: **topic area**, **nature of error** (factual, outdated, misunderstanding, incomplete), **correct information** (if provided). Ask for clarification if too vague.

### 2. Load Relevant KB (Full Scrutiny)

Spawn a [scouter](../agents/scouter.md) in normal mode with the error as query (SKILL.md §3). Look for:
- Statements contradicting the correction
- Incomplete/misleading statements
- Related notes with the same error
- Skill files (`SKILL.md`, `reference/`, `agents/`) if topic has `skill/` subfolder
- **Evolution**: If the error is actually outdated terminology or a renamed/superseded concept, follow [evolution-workflow.md](evolution-workflow.md) instead

### 3. Identify the Error

Present: found locations (note + line + quoted content), proposed corrections, description adjustments. If error not found in KB, inform user and offer to add correct info as new note.

### 4. Await Approval

Use SKILL.md shared approval procedure.

### 5. Apply Corrections

For each corrected note:
1. Fix the incorrect content
2. Add `## Contents` if >100 lines and missing
3. Add correction callout after corrected section:
   ```markdown
   > [!correction] {{DATE}}
   > Previously stated X. Corrected to Y because Z.
   ```
4. Update `description` in frontmatter if meaning changed
5. Add new references under `## References` (not frontmatter)
