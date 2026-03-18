---
name: kb-monitor - Index
description: Index for the kb-monitor skill — monitors KB usage patterns and skill health, recommends skill conversions for frequently-accessed content, tracks cross-session observations via dual-layer decision model (hooks + memory).
---

# kb-monitor - Index

The kb-monitor skill observes KB access patterns across sessions and skill correction signals to identify two types of optimization opportunities:

1. **Skill candidates** — KB topics read frequently across sessions that would benefit from skill conversion (progressive disclosure, scripts, structured references)
2. **Skill health issues** — existing skills that accumulate user corrections, suggesting drift from correctness

## Architecture

Uses a **dual-layer decision model**:
- **Hooks** = signal layer (always-on data collection via PostToolUse tracking)
- **Memory** = policy layer (gates/filters: exclusions, cooldowns, conditions)

A recommendation surfaces only when both layers agree: hook data crosses a threshold AND memory has no blocking policy.

## Triggering

| Trigger | Mechanism | When |
|---------|-----------|------|
| Session start | SessionStart hook runs `analyze_access.py` | Every session |
| Mid-conversation | `track_kb_access.py` checks in-session threshold | After 5+ reads of same non-skill topic |
| User request | Description-based matching or explicit `/kb-monitor` | On demand |

## Skill

Full procedures, agent definitions, scripts, and reference files: [`skill/SKILL.md`](skill/SKILL.md)

### Skill Contents

**Agents:**

| Agent | Model | Purpose |
|-------|-------|---------|
| [analyzer](skill/agents/analyzer.md) | haiku | Read access log, compute topic scores, identify candidates |

**References:**

| Reference | Purpose |
|-----------|---------|
| [scoring-rules](skill/reference/scoring-rules.md) | Thresholds and scoring criteria for recommendations |

**Scripts:**

| Script | Purpose |
|--------|---------|
| [track_kb_access.py](skill/scripts/track_kb_access.py) | Async PostToolUse hook: logs KB reads to JSONL |
| [analyze_access.py](skill/scripts/analyze_access.py) | CLI: query access log, compute candidates, check health |

## Related Topics

- [kb-learn](../learn/index.md) — KB management skill (create/update/correct)
- [kb-find](../find/index.md) — Read-only KB discovery skill
- [kb-mint](../mint/index.md) — Skill conversion and plugin packaging (monitoring delegates `--convert` here)
