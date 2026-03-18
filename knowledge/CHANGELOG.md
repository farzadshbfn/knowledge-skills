# Changelog

## 2026-03-18 -- [fix] Remove curl-pipe-sh pattern from kb-bootstrap

Replaced `curl | sh` uv install instruction with package manager alternatives (brew, pip) and a link to official docs. Fixes Snyk E005 security finding.

- UPDATE: `bootstrap/skill/SKILL.md`

## 2026-03-18 -- [create] Knowledge-skills repo

Extracted KB management skills from BusinessAI into a standalone, self-contained repo.

- CREATE: `bootstrap/` — first-time KB setup (config, directories, CLAUDE.md injection)
- CREATE: `compact/` — KB directory compaction (legacy extraction, terminology unification, note splitting)
- CREATE: `find/` — read-only KB discovery with progressive 4-tier loading
- CREATE: `learn/` — KB content management (article, topic, fix workflows, structure conventions)
- CREATE: `mint/` — KB-to-skill-to-plugin pipeline (skill conversion, plugin packaging)
- CREATE: `monitor/` — KB usage monitoring and skill gardening (access tracking, health checks)
- CREATE: `view/` — local HTML viewer (browse, search, visualize KBs in browser)
