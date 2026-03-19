---
name: kb-bootstrap
description: Sets up the knowledge base for a project. Creates the KB config, directory structure, and appends minimal instructions to the project's CLAUDE.md. Run this once when first using KB skills in a new project.
argument-hint: "[kb-path]"
---

# /kb-bootstrap — KB Setup

Sets up KB configuration and appends minimal instructions to the project's CLAUDE.md.

## 1. Check Prerequisites

Run `which uv`. If not found:

> `uv` is required but not installed. Install it via your package manager:
> ```bash
> brew install uv        # macOS
> pip install uv         # pip
> ```
> See [uv installation docs](https://docs.astral.sh/uv/getting-started/installation/) for other methods.
> Then restart your terminal and re-run `/kb-bootstrap`.

Stop if `uv` is not available.

## 2. Check Existing Config

Check if `.claude/knowledge-base/config.json` already exists.

- **Exists**: Tell user "KB is already configured." Show current `kb_roots` entries. Ask if they want to add another KB or re-run the CLAUDE.md update. If neither, stop.
- **Does not exist**: Continue to Step 3.

## 3. Choose KB Location

If `$ARGS` provides a path, use it. Otherwise, ask the user using AskUserQuestion:

- Options: "Use ./knowledge/ (Recommended)", "Custom path"
- If custom: ask for the path

## 4. Create Config and Structure

1. Create `.claude/knowledge-base/config.json`:
   ```json
   {
     "kb_roots": [
       { "name": "core", "path": "./<chosen-path>" }
     ]
   }
   ```

2. Create the KB directory and `CHANGELOG.md`:
   ```
   <kb-path>/
   └── CHANGELOG.md
   ```

3. Initialize `CHANGELOG.md`:
   ```markdown
   # Changelog
   ```

## 5. Update CLAUDE.md

Read the project's `CLAUDE.md` (if it exists). Append the content from [assets/claude-md-snippet.md](assets/claude-md-snippet.md) — do NOT replace existing content. If the file doesn't exist, create it with only the snippet content.

## 6. Install Skill Hooks

Install PostToolUse validation hooks directly into skill SKILL.md frontmatters so they work automatically when the skill runs.

### 6a. Locate installed skills

Find the skill directories by checking these locations (first match wins):
1. `.claude/skills/` (project-local)
2. `~/.claude/skills/` (user-global)

Verify that `kb-learn`, `kb-compact`, `kb-mint`, and `kb-monitor` exist there.

### 6b. Update skill frontmatters

The skills ship with PostToolUse validation hooks in their frontmatter using `${CLAUDE_SKILL_DIR}` paths (which may not be substituted in frontmatter yet — see [#36135](https://github.com/anthropics/claude-code/issues/36135)). Rewrite the hook commands with concrete paths so they work immediately.

For each of these three SKILL.md files (under the location found in 6a):
- `kb-learn/SKILL.md`
- `kb-compact/SKILL.md`
- `kb-mint/SKILL.md`

Find the `hooks:` block in the frontmatter and replace the `command:` value with the concrete path to `validate_kb.py --hook` using the location from 6a.

### 6c. Suggest monitoring hooks

SessionStart and PreCompact hooks cannot live in skill frontmatter — suggest adding them to settings. Use the `kb-monitor/scripts/analyze_access.py` path from the location found in 6a.

These hooks analyze KB access patterns to surface topics worth converting to skills and flag skill health issues. They run at session start and before context compaction. Without them, you won't get proactive recommendations (you'd have to manually run `/kb-monitor`), and monitoring observations from earlier in the conversation are lost when context is compressed.

> **Recommended**: Add these monitoring hooks to your project settings (`.claude/settings.json`) for session-start analysis and pre-compaction context:
>
> ```json
> {
>   "hooks": {
>     "SessionStart": [
>       {
>         "hooks": [
>           {
>             "type": "command",
>             "command": "uv run <skills-location>/kb-monitor/scripts/analyze_access.py --candidates --health --format=context"
>           }
>         ]
>       }
>     ],
>     "PreCompact": [
>       {
>         "hooks": [
>           {
>             "type": "command",
>             "command": "uv run <skills-location>/kb-monitor/scripts/analyze_access.py --candidates --health --format=context",
>             "async": true
>           }
>         ]
>       }
>     ]
>   }
> }
> ```
>
> Replace `<skills-location>` with the path from 6a.

Use AskUserQuestion: "Add monitoring hooks to project settings", "Add to user settings", "Skip".

If the user chooses to add, read the target settings file (create `{"hooks":{}}` if missing), merge the SessionStart and PreCompact hooks — do NOT overwrite existing hooks.

### 6d. Suggest validation hooks for settings

The skills already have PostToolUse validation hooks in their frontmatter (updated in 6b), so KB changes through `/kb-learn`, `/kb-compact`, and `/kb-mint` are already covered. However, an agent might directly edit a KB file without going through a skill. Adding the same PostToolUse hook to settings catches those cases too. Good to have, but not a must.

> **Optional**: Add a global validation hook to catch direct KB edits outside of skills:
>
> ```json
> {
>   "hooks": {
>     "PostToolUse": [
>       {
>         "matcher": "Write|Edit|Bash",
>         "hooks": [
>           {
>             "type": "command",
>             "command": "uv run <skills-location>/kb-learn/scripts/validate_kb.py --hook"
>           }
>         ]
>       }
>     ]
>   }
> }
> ```
>
> Replace `<skills-location>` with the path from 6a.

Use AskUserQuestion: "Add validation hook to project settings", "Add to user settings", "Skip".

If the user chooses to add, merge into the same settings file used in 6c — do NOT overwrite existing hooks.

## 7. Confirm

Tell the user: "KB is set up. You can start learning with `/kb-learn`."
