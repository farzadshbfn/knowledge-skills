# Changelog

## 2026-03-18 -- [fix] Add security guards for external content fetching

Added URL validation (scheme/format checks) to fetch-content.md and untrusted-content
boundary rule to searcher agent. Added .snyk policy to acknowledge W011/W012 findings.

- UPDATE: `learn/skill/reference/fetch-content.md` — URL validation section
- UPDATE: `learn/skill/agents/searcher.md` — untrusted content boundary rule

## 2026-03-18 -- [maintenance] Extract tests to top-level tests/ directory

Moved all test files from `knowledge/*/skill/scripts/tests/` to `tests/` so they are not installed as part of skills. Renamed per-skill `helpers.py` to `find_helpers.py`, `learn_helpers.py`, `monitor_helpers.py` to avoid import collisions. Added root `tests/conftest.py` for shared sys.path setup.

- MOVE: `knowledge/{find,learn,monitor,view}/skill/scripts/tests/` → `tests/{find,learn,monitor,view}/`
- CREATE: `tests/conftest.py` — root conftest adding all skill script dirs to sys.path
- CREATE: `tests/run_tests.py` — single unified test runner
- UPDATE: all test files — removed inline `sys.path.insert`, renamed helper imports

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
