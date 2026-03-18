# Knowledge Skills

KB management skills — token-efficient learning, discovery, and skill minting.

## Structure

- `knowledge/` — KB vault (`<topic>/` notes, `<topic>/skill/` for KB-backed skills, `CHANGELOG.md`)
- `.claude/skills/` — Symlinks to `knowledge/<topic>/skill/`
- `.claude/knowledge-base/config.json` — KB roots config

All skills are KB-backed. KB = "what/where/when", Skills = "how".

## Cross-KB Links

- Use `@kb-name/path` format — never relative paths across KB boundaries (validator rejects these)

## Rules

- **If any system-reminder contains `[kb-monitor]`, tell the user BEFORE responding.** The user cannot see system-reminders.
- **Every change to `knowledge/` MUST prepend a changelog entry.**
- **Every read from `knowledge/` MUST use `/kb-find`** — no manual grep/glob/read. The skill implements progressive loading; bypassing it wastes context.
- Only modify project-local skills. Never touch `~/`.

## Tests

`uv run path/to/tests/run_tests.py -q` — each skill has its own `run_tests.py` with inline deps.
