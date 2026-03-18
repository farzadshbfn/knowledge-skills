
## Knowledge Base

KB config: `.claude/knowledge-base/config.json`

### Commands

| Command | Purpose |
|---------|---------|
| `/kb-bootstrap` | First-time KB setup (config, directories, CLAUDE.md) |
| `/kb-learn` | Learn from articles, research topics, fix KB errors |
| `/kb-find` | Look up existing KB content (read-only) |
| `/kb-compact` | Compact KB directories (split, merge, unify) |
| `/kb-mint` | Convert KB topics to skills, package as plugins |
| `/kb-view` | Open KB viewer in browser |
| `/kb-monitor` | Check KB health and skill candidates |

### Rules

- Every change to the knowledge folder MUST prepend a changelog entry to `<kb-root>/CHANGELOG.md`
- Every read from the knowledge folder MUST use `/kb-find` — do not manually grep/glob/read KB content
