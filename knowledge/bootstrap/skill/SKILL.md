---
name: kb-bootstrap
description: Sets up the knowledge base for a project or initializes the global (god) KB config. Creates the KB config, directory structure, and appends minimal instructions to the project's CLAUDE.md. Run this once when first using KB skills in a new project. Use --global to set up the global read-only KB.
argument-hint: "[kb-path | --global]"
effort: low
---

# /kb-bootstrap — KB Setup

Sets up KB configuration and appends minimal instructions to the project's CLAUDE.md.

## 0. Routing

Parse `$ARGS`:
- If `--global` is present → follow **Section G** (Global KB Setup), then stop.
- Otherwise → continue with Section 1 (Project KB Setup).

---

# Project KB Setup

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

## 6. Suggest Optional Hooks

Skill frontmatters already include PostToolUse validation hooks using `${CLAUDE_SKILL_DIR}` — these work automatically. This section offers optional hooks for settings.json (monitoring + catch-all validation).

### 6a. Locate installed skills

Run `uv run ${CLAUDE_SKILL_DIR}/scripts/resolve_skill_paths.py` to locate installed kb-skills and resolve script paths. The script checks project-local (`.claude/skills/`) then user-global (`~/.claude/skills/`).

Output is JSON with these fields:
- `skills_dir` — where kb-skills are installed
- `validation` — resolved path to `validate_kb.py`
- `monitoring` — resolved paths to monitoring scripts (`null` if kb-monitor not installed)

**If the script exits with code 1**: `kb-learn` is missing — stop and tell the user KB skills are not installed.

**If monitoring paths are null**: tell the user monitoring features won't be available (6b will be skipped).

### 6b. Suggest monitoring hooks

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

### 6c. Suggest validation hooks for settings

The skills already have PostToolUse validation hooks in their frontmatter, so KB changes through `/kb-learn`, `/kb-compact`, and `/kb-mint` are already covered. However, an agent might directly edit a KB file without going through a skill. Adding the same PostToolUse hook to settings catches those cases too. Good to have, but not a must.

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

If the user chooses to add, merge into the same settings file used in 6b — do NOT overwrite existing hooks.

## 7. Confirm

Tell the user: "KB is set up. If you added settings hooks, restart Claude Code to pick them up. Start learning with `/kb-learn`."

---

# Section G — Global KB Setup (`--global`)

Sets up the global (god) KB config at `~/.claude/knowledge-base/config.json`. This config makes KBs available as read-only across all projects.

## G1. Check Prerequisites

Run `which uv`. If not found, show the same install message as Section 1 and stop.

## G2. Check Existing Global Config

Check if `~/.claude/knowledge-base/config.json` already exists.

- **Exists**: Read and show current config (namespace + kb_roots). Ask using AskUserQuestion:
  - "Add another KB root"
  - "Done"
  - If "Add another KB root" → go to G3b.
  - If "Done" → stop.
- **Does not exist**: Continue to G3.

## G3. Choose Namespace

Ask the user using AskUserQuestion:

- "Use `god` (Recommended)" — the default namespace
- "Custom namespace" — ask for the name

The namespace is a prefix that disambiguates global KB names from project KB names (e.g., namespace `god` + KB name `core` → `god.core`).

## G3b. Choose Source Project

Ask the user for the path to the KB project that should be used as the global source. This must be an existing project with its own `.claude/knowledge-base/config.json`.

Validate:
- Path must exist and be a directory.
- `<path>/.claude/knowledge-base/config.json` must exist. If not, tell the user: "Run `/kb-bootstrap` inside that project first to set it up, then re-run `/kb-bootstrap --global`."

## G4. Create Global Config

1. Create `~/.claude/knowledge-base/` directory if needed.

2. Write `~/.claude/knowledge-base/config.json`:
   ```json
   {
     "namespace": "<chosen-namespace>",
     "source": "<source-project-path>"
   }
   ```

   The global config just references the source project. All KB roots are read from the source project's own config at runtime — no duplication.

3. Create `~/.claude/knowledge-base/suggestions/` directory for the suggestion pipeline.

## G5. Confirm

Tell the user:

> Global KB configured. All projects will now see KBs from `<source-path>` as read-only with `@<namespace>.*` prefix.
>
> - Global config: `~/.claude/knowledge-base/config.json`
> - Source project: `<source-path>`
> - Suggestions: `~/.claude/knowledge-base/suggestions/`
>
> Use `see: @<namespace>.<kb-name>/topic` in project notes to reference global KB content.
> To manage the global KB, work inside the source project directly.
