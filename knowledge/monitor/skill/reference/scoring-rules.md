# Scoring Rules

Thresholds and criteria for kb-monitor recommendations.

## Skill Candidate Thresholds

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| Unique sessions | >= 3 | Topic is accessed repeatedly, not a one-off read |
| Total reads | >= 9 | Volume confirms sustained interest |
| In-session reads | >= 3 | Mid-conversation signal (same session, no skill/) |
| Has skill/ | false | Only suggest for topics without existing skills |

A topic must meet ALL cross-session thresholds (sessions AND reads) to qualify as a candidate. In-session threshold triggers a mid-conversation recommendation independently.

## Skill Health Thresholds

| Metric | Threshold | Status |
|--------|-----------|--------|
| Corrections (30d) | 1-2 | watch — note but don't act |
| Corrections (30d) | >= 3 | action — recommend fix |

Corrections are tracked in the memory file, not the access log. They come from user interactions where the user corrects skill output.

## Policy Gate Rules

| Gate Type | Behavior | Duration |
|-----------|----------|----------|
| exclude | Never surface | Permanent (until user removes) |
| cooldown | Skip N sessions | Counted from set date |
| condition | Skip until condition met | Until user confirms |
| throttle | Rate limit | Per-session cap |

Global throttle: max 1 conversion suggestion per session (prevents noise).

## Score Computation

For SessionStart and mid-conversation checks:

1. Read access log, aggregate by topic (unique sessions, total reads)
2. Filter: only topics without skill/ folders
3. Apply thresholds: sessions >= 3 AND reads >= 9
4. Check memory policy gates: exclude any gated topics
5. Sort by session count (descending), then reads (descending)
6. Output top candidates (max 3 per session)
