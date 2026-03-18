---
name: kb-bootstrap
description: Sets up the knowledge base for a project. Creates the KB config, directory structure, and appends minimal instructions to the project's CLAUDE.md. Run this once when first using KB skills in a new project.
argument-hint: "[kb-path]"
---

# /kb-bootstrap — KB Setup

Sets up KB configuration and appends minimal instructions to the project's CLAUDE.md.

## 1. Check Prerequisites

Run `which uv`. If not found:

> `uv` is required but not installed. Install it with:
> ```bash
> curl -LsSf https://astral.sh/uv/install.sh | sh
> ```
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

## 6. Confirm

Tell the user: "KB is set up. You can start learning with `/kb-learn`."
