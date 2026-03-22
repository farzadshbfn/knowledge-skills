# Changelog

## 2026-03-22 -- [feat] Improve kb-learn content reliability

Added challenger agent for adversarial web research against claims (topic workflow).
Lowered assessor trigger threshold to always run for any non-KNOWN claims. Added
corroboration requirement (2+ independent sources for CONFIRMED/LIKELY verdicts).
Introduced per-claim inline confidence markers (`<conf:high>`, `<conf:medium>`,
`<conf:low>`) with validator support. Untagged claims are treated as medium
confidence. Approval flow now separates low-confidence claims and excludes
them by default.

CREATE: learn/skill/agents/challenger.md
UPDATE: learn/skill/agents/assessor.md
UPDATE: learn/skill/agents/searcher.md
UPDATE: learn/skill/SKILL.md
UPDATE: learn/skill/reference/article-workflow.md
UPDATE: learn/skill/reference/topic-workflow.md
UPDATE: learn/skill/assets/topic-note.md
UPDATE: learn/skill/scripts/validate_kb.py

## 2026-03-19 -- [feat] Add resolve_skill_paths script and restart hint

Added bootstrap/scripts/resolve_skill_paths.py to locate installed skills
and resolve script paths. Bootstrap Step 7 now recommends restarting Claude Code.

## 2026-03-19 -- [feat] Bootstrap installs PostToolUse hooks into skill frontmatters

Reworked Step 6: bootstrap now resolves the real path to validate_kb.py and
writes PostToolUse hooks directly into learn, compact, mint SKILL.md frontmatters.
SessionStart and PreCompact monitoring hooks remain as suggestions for settings.json.

## 2026-03-19 -- [fix] Add missing SessionStart and PreCompact hooks to kb-bootstrap

Bootstrap Step 6 only suggested PostToolUse hooks. Added the monitoring hooks
(SessionStart + PreCompact running analyze_access.py) that were missing.

## 2026-03-19 -- [fix] Move validation from frontmatter hooks to skill body

Removed PostToolUse hooks from SKILL.md frontmatter (broken: `${CLAUDE_SKILL_DIR}`
not substituted in frontmatter hooks, [#36135](https://github.com/anthropics/claude-code/issues/36135)).
Added explicit validation sections to skill bodies where `${CLAUDE_SKILL_DIR}` works.
Updated bootstrap to suggest users add hooks to their system settings.

- UPDATE: `learn/skill/SKILL.md` — removed frontmatter hook, added §7 Validation
- UPDATE: `compact/skill/SKILL.md` — removed frontmatter hook, added §7 Validation
- UPDATE: `compact/skill/agents/compacter.md` — removed frontmatter hook
- UPDATE: `mint/skill/SKILL.md` — added §5 Validation
- UPDATE: `bootstrap/skill/SKILL.md` — added §6 suggesting hooks setup
- UPDATE: `monitor/skill/agents/analyzer.md` — use `${CLAUDE_SKILL_DIR}` instead of hardcoded path

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
