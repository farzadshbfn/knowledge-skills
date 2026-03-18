---
name: kb-monitor
description: Monitors KB usage patterns and skill health. Activates when KB access tracking detects frequently-read content that could become a skill, or when user corrections suggest a skill is underperforming. Also triggers on `this isn't working right`, `this skill keeps getting X wrong`, `convert this to a skill`, or `what should become a skill`. Tracks cross-session observations via memory.
argument-hint: "[--status | --convert <topic-path> | --health <skill-name>]"
---

# /kb-monitor — KB Usage Monitoring & Skill Gardening

## 1. Routing

Parse `$0` (the first argument) to determine the mode:

- **If `$0` is `--status` or empty (default/proactive activation)**: Follow Section 3 (Status Mode).
- **If `$0` is `--convert`**: Follow Section 4 (Convert Mode). `$1` is the topic path.
- **If `$0` is `--health`**: Follow Section 5 (Health Mode). `$1` is the skill name.
- **Otherwise**: Show usage:
  ```
  Usage: /kb-monitor [mode]

  Modes:
    --status                     Show candidates + health (default)
    --convert <topic-path>       Convert KB topic to skill
    --health <skill-name>        Check skill health + correction history

  Examples:
    /kb-monitor
    /kb-monitor --convert claude/mcp/
    /kb-monitor --health writing-article
  ```

## 1a. Target Format Awareness

When recommending or executing conversions, consider the target environment:

| Environment | Recommendation | Delegate to |
|-------------|---------------|-------------|
| Standalone project (default) | Convert to KB-backed skill | `/kb-mint --skill` |
| Plugin distribution | Convert to skill, then package as plugin | `/kb-mint --skill` then `/kb-mint --plugin` |
| Cowork plugin | Convert to skill, then package with Cowork additions | `/kb-mint --skill` then `/kb-mint --cowork` |

Detect environment from context: if the project has a `.claude-plugin/plugin.json`, it's a plugin project. If skills reference Cowork connectors or the project targets Cowork, recommend the Cowork path.

For plugin projects, also track **plugin candidates** — groups of related skills that could be bundled under a shared namespace. A group becomes a plugin candidate when 3+ skills share a common category prefix.

## 2. References

| Reference | Purpose |
|-----------|---------|
| [scoring-rules](reference/scoring-rules.md) | Thresholds and scoring criteria for candidates and health |

## 2a. Data Sources

### Access Log

Run `analyze_access.py` to query the access log without loading it into context:
```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/analyze_access.py --top-topics --candidates --health --format=json
```
Output is compact JSON (~50-100 tokens).

### Memory

Read the memory file at the standard Claude memory location for this project. Look for `monitoring_kb_observations.md`. This contains:
- Skill candidate tracking (KB topics, session counts, status)
- Skill health tracking (corrections, status)
- Conversion history
- Policy gates (exclude, cooldown, condition, throttle)

## 2a. Agents

| Agent | Model | Purpose | Used by |
|-------|-------|---------|---------|
| [analyzer](agents/analyzer.md) | haiku | Compute access scores from raw log | --status (optional, for large logs) |

Use the analyzer agent when the access log is large (1000+ entries). For most cases, the `analyze_access.py` CLI output is sufficient.

## 3. Status Mode (`--status`)

1. **Gather data**: Run `analyze_access.py --top-topics --candidates --health --format=json`
2. **Read memory**: Load `monitoring_kb_observations.md` from memory directory
3. **Present findings**:

   **Skill Candidates:**
   For each candidate topic (high read count, no `skill/` folder):
   - Topic name, session count, total reads
   - Whether memory has any gate (cooldown, exclude, condition)
   - Recommendation: "Convert?", "Skip", "Never for this topic"

   **Skill Health Issues:**
   For each skill with corrections in memory:
   - Skill name, correction count, last issue description
   - Status: `watch` (1-2 corrections), `action` (3+ corrections)
   - Recommendation: "Fix?", "Skip", "Mark resolved"

   **Recent Conversions:**
   List from memory's Conversion History table.

4. **Prompt for action**: Use `AskUserQuestion` to ask the user what to do with each candidate/issue. Present the options clearly (Convert / Fix / Skip / Never / Not now / Wait until condition). Then process:
   - "Convert" → Switch to Section 4 (Convert Mode) for that topic
   - "Fix" → Switch to Section 5 (Health Mode) for that skill
   - "Skip" → No action, no memory update
   - "Never" → Add `exclude` gate to memory's Policy Gates table
   - "Not now" → Add `cooldown` gate with session count to memory
   - "Wait until \<condition\>" → Add `condition` gate to memory

5. **Update memory**: After each interaction, update `monitoring_kb_observations.md`:
   - Update candidate session counts and statuses
   - Record any new policy gates
   - Keep under 100 lines (archive old entries)

## 4. Convert Mode (`--convert <topic-path>`)

Delegate the actual conversion to `/kb-mint`:

```
/kb-mint --skill <topic-path>
```

After kb-mint completes the conversion:

1. **Update monitoring memory**: Add conversion record to memory's Conversion History table
2. **Remove from candidates**: Remove the topic from Skill Candidates table
3. **If plugin project**: Suggest follow-up: `/kb-mint --plugin <new-skill-name>` (in plugin contexts, use the namespaced form instead)

## 5. Health Mode (`--health <skill-name>`)

1. **Read memory**: Load correction history for this skill from `monitoring_kb_observations.md`
2. **Read skill files**: Load the skill's `SKILL.md` and key reference files
3. **Present health summary**:
   - Correction count (30-day window)
   - Specific issues from memory's Skill Health table
   - Comparison between recorded issues and current skill content
4. **Offer remediation**: Use `AskUserQuestion` to ask the user which action to take:
   - "Fix" → Run `/kb-learn fix` with pre-filled description constructed from correction history
   - "Mark resolved" — if issues have been fixed
   - "Skip" — no action
5. **Update memory**: Record health check, update status

## 6. Memory Management

### Memory File Location

Standard Claude memory: `~/.claude/projects/<project-key>/memory/monitoring_kb_observations.md`

### Memory File Structure

```markdown
---
name: kb-monitoring-observations
description: Cross-session KB access patterns, skill health scores, conversion history, and pending recommendations
type: project
---

# KB Monitoring Observations

## Skill Candidates
| KB Topic | First Seen | Sessions | Status |
|----------|-----------|----------|--------|

## Skill Health
| Skill | Corrections (30d) | Last Issue | Status |
|-------|-------------------|------------|--------|

## Conversion History
| Topic | Converted | Skill Name |
|-------|-----------|------------|

## Policy Gates
| Topic/Skill | Gate Type | Condition | Set On |
|-------------|-----------|-----------|--------|
| * (global) | throttle | max 1 conversion suggestion per session | — |
```

### Gate Types

- **exclude**: Never surface this topic/skill (permanent)
- **cooldown**: Wait N more sessions before resurfacing
- **condition**: Don't surface until free-text condition is met
- **throttle**: Global rate limits on recommendation frequency

### Housekeeping

- Keep memory file under 100 lines
- Archive old conversion history entries (older than 90 days)
- Remove stale cooldowns when session count is met
- Remove conditions when user confirms they're resolved
