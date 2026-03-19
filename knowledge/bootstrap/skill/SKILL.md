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

## 6. Suggest Hooks

After setup, suggest the user add validation and monitoring hooks to their settings. Present this as optional but recommended:

> **Recommended**: Add these hooks to your Claude Code settings for automatic KB validation and access tracking.
> You can add them to project settings (`.claude/settings.json`) or user settings (`~/.claude/settings.json`).
>
> ```json
> {
>   "hooks": {
>     "PostToolUse": [
>       {
>         "matcher": "Read",
>         "hooks": [
>           {
>             "type": "command",
>             "command": "uv run ${CLAUDE_SKILL_DIR}/scripts/track_kb_access.py",
>             "async": true
>           }
>         ]
>       },
>       {
>         "matcher": "Write|Edit|Bash",
>         "hooks": [
>           {
>             "type": "command",
>             "command": "uv run ${CLAUDE_SKILL_DIR}/scripts/validate_kb.py --hook"
>           }
>         ]
>       }
>     ],
>     "SessionStart": [
>       {
>         "hooks": [
>           {
>             "type": "command",
>             "command": "uv run ${CLAUDE_SKILL_DIR}/scripts/analyze_access.py --candidates --health --format=context"
>           }
>         ]
>       }
>     ],
>     "PreCompact": [
>       {
>         "hooks": [
>           {
>             "type": "command",
>             "command": "uv run ${CLAUDE_SKILL_DIR}/scripts/analyze_access.py --candidates --health --format=context",
>             "async": true
>           }
>         ]
>       }
>     ]
>   }
> }
> ```
>
> **Note:** `${CLAUDE_SKILL_DIR}` substitution in skill hooks is currently broken ([#36135](https://github.com/anthropics/claude-code/issues/36135)). Until fixed, replace `${CLAUDE_SKILL_DIR}` with the absolute path to the skill's `kb-monitor/` and `kb-learn/` directories. For example:
> - `uv run /path/to/kb-monitor/skill/scripts/track_kb_access.py`
> - `uv run /path/to/kb-learn/skill/scripts/validate_kb.py --hook`
> - `uv run /path/to/kb-monitor/skill/scripts/analyze_access.py --candidates --health --format=context`

Use AskUserQuestion: "Add hooks to project settings", "Add hooks to user settings", "Skip for now".

If the user chooses to add hooks, use the absolute resolved paths of the installed skills (check both `.claude/skills/kb-monitor` and `~/.claude/skills/kb-monitor`, resolve symlinks). Write the hooks into the chosen settings file, merging with any existing hooks.

## 7. Confirm

Tell the user: "KB is set up. You can start learning with `/kb-learn`."
