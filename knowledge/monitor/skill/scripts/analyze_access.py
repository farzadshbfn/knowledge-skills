#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""analyze_access.py — Query and summarize KB access log.

CLI tool for querying .claude/knowledge-base/access-log.jsonl.
Used by SessionStart hook (--format=context) and manual queries (--format=json).
Implements the dual-layer decision model: hook signals + memory policy gates.
"""

import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


LOG_FILE = ".claude/knowledge-base/access-log.jsonl"
DEFAULT_CANDIDATE_SESSIONS = 3
DEFAULT_CANDIDATE_READS = 9


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class TopicStats:
    topic: str
    sessions: int = 0
    reads: int = 0
    last_read: str = ""
    has_skill: bool = False


@dataclass
class HealthEntry:
    skill: str
    corrections: int = 0
    last_issue: str = ""
    status: str = "ok"


@dataclass
class AnalysisResult:
    top_topics: list[TopicStats] = field(default_factory=list)
    candidates: list[TopicStats] = field(default_factory=list)
    health: list[HealthEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Log loading and aggregation
# ---------------------------------------------------------------------------

def load_log(cwd: str) -> list[dict]:
    """Load and parse the access log."""
    log_path = os.path.join(cwd, LOG_FILE)
    entries = []
    try:
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except FileNotFoundError:
        pass
    return entries


def compute_topic_stats(entries: list[dict], cwd: str) -> list[TopicStats]:
    """Aggregate entries by topic."""
    topic_sessions: dict[str, set[str]] = defaultdict(set)
    topic_reads: dict[str, int] = defaultdict(int)
    topic_last: dict[str, str] = {}

    for entry in entries:
        topic = entry.get("topic", "")
        sid = entry.get("sid", "")
        ts = entry.get("ts", "")
        if topic:
            topic_sessions[topic].add(sid)
            topic_reads[topic] += 1
            if ts > topic_last.get(topic, ""):
                topic_last[topic] = ts

    stats = []
    for topic in sorted(
        topic_sessions, key=lambda t: len(topic_sessions[t]), reverse=True
    ):
        stats.append(TopicStats(
            topic=topic,
            sessions=len(topic_sessions[topic]),
            reads=topic_reads[topic],
            last_read=topic_last.get(topic, ""),
            has_skill=_topic_has_skill(topic, cwd),
        ))
    return stats


def find_candidates(
    stats: list[TopicStats],
    cwd: str,
    min_sessions: int = DEFAULT_CANDIDATE_SESSIONS,
    min_reads: int = DEFAULT_CANDIDATE_READS,
) -> list[TopicStats]:
    """Find topics that qualify as skill candidates (both layers must agree)."""
    candidates = []
    for s in stats:
        if s.has_skill:
            continue
        if s.sessions >= min_sessions and s.reads >= min_reads:
            if not _is_gated(s.topic, cwd):
                candidates.append(s)
    return candidates


# ---------------------------------------------------------------------------
# Health data (from memory)
# ---------------------------------------------------------------------------

def load_health(cwd: str) -> list[HealthEntry]:
    """Load skill health data from memory file."""
    memory_dir = _find_memory_dir(cwd)
    if not memory_dir:
        return []

    memory_file = os.path.join(memory_dir, "monitoring_kb_observations.md")
    try:
        with open(memory_file) as f:
            content = f.read()
    except FileNotFoundError:
        return []

    entries = []
    in_health = False
    for line in content.split("\n"):
        if "## Skill Health" in line:
            in_health = True
            continue
        if in_health and line.startswith("## "):
            break
        if not in_health or not line.startswith("|") or "---" in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        # Expected: | Skill | Corrections | Last Issue | Status |
        if len(parts) >= 6 and parts[1] != "Skill":
            try:
                corrections = int(parts[2])
            except ValueError:
                corrections = 0
            entries.append(HealthEntry(
                skill=parts[1],
                corrections=corrections,
                last_issue=parts[3],
                status=parts[4],
            ))
    return entries


# ---------------------------------------------------------------------------
# Analysis orchestrator
# ---------------------------------------------------------------------------

def analyze(
    cwd: str,
    include_top: bool = False,
    include_candidates: bool = False,
    include_health: bool = False,
) -> AnalysisResult:
    """Run analysis and return results."""
    result = AnalysisResult()
    entries = load_log(cwd)
    stats = compute_topic_stats(entries, cwd)

    if include_top:
        result.top_topics = stats[:10]
    if include_candidates:
        result.candidates = find_candidates(stats, cwd)
    if include_health:
        result.health = load_health(cwd)

    return result


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def format_json(result: AnalysisResult) -> str:
    """Format result as compact JSON."""
    output: dict = {}
    if result.top_topics:
        output["top_topics"] = [
            {"topic": s.topic, "sessions": s.sessions, "reads": s.reads,
             "has_skill": s.has_skill}
            for s in result.top_topics
        ]
    if result.candidates:
        output["candidates"] = [
            {"topic": s.topic, "sessions": s.sessions, "reads": s.reads}
            for s in result.candidates
        ]
    if result.health:
        output["health"] = [
            {"skill": h.skill, "corrections": h.corrections,
             "last_issue": h.last_issue, "status": h.status}
            for h in result.health
        ]
    return json.dumps(output)


def format_context(result: AnalysisResult) -> str:
    """Format result as context line for SessionStart hook.

    Returns empty string when no recommendations pass both layers.
    """
    parts = []
    if result.candidates:
        n = len(result.candidates)
        top = result.candidates[0]
        detail = f"{top.topic}/ ({top.sessions} sessions, {top.reads} reads"
        if n > 1:
            detail += f", +{n - 1} more"
        detail += " — no memory block)"
        parts.append(f"{n} skill candidate{'s' if n > 1 else ''}: {detail}")

    health_issues = [h for h in result.health if h.status in ("watch", "action")]
    if health_issues:
        n = len(health_issues)
        top = health_issues[0]
        parts.append(
            f"{n} health issue{'s' if n > 1 else ''}: "
            f"/{top.skill} ({top.corrections} corrections, {top.status} status)"
        )

    if not parts:
        return ""

    return (
        f"[kb-monitor] {'. '.join(parts)}. "
        f"Run /kb-monitor for details."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _topic_has_skill(topic: str, cwd: str) -> bool:
    """Check if a KB topic already has a skill/ folder."""
    config_path = os.path.join(cwd, ".claude/knowledge-base/config.json")
    try:
        with open(config_path) as f:
            config = json.load(f)
        for entry in config.get("kb_roots", []):
            root = entry["path"].lstrip("./")
            skill_dir = os.path.join(cwd, root, topic, "skill")
            if os.path.isdir(skill_dir):
                return True
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        if os.path.isdir(os.path.join(cwd, "knowledge", topic, "skill")):
            return True
    return False


def _is_gated(topic: str, cwd: str) -> bool:
    """Check if topic is blocked by a memory policy gate."""
    memory_dir = _find_memory_dir(cwd)
    if not memory_dir:
        return False

    memory_file = os.path.join(memory_dir, "monitoring_kb_observations.md")
    try:
        with open(memory_file) as f:
            content = f.read()
    except FileNotFoundError:
        return False

    in_gates = False
    for line in content.split("\n"):
        if "## Policy Gates" in line:
            in_gates = True
            continue
        if in_gates and line.startswith("## "):
            break
        if not in_gates:
            continue
        if f"{topic}/" in line or f"| {topic} " in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 4:
                gate_type = parts[2].lower()
                if any(g in gate_type for g in ("exclude", "cooldown", "condition")):
                    return True
    return False


def _find_memory_dir(cwd: str) -> str | None:
    """Find the Claude memory directory for this project."""
    home = os.path.expanduser("~")
    project_key = cwd.replace("/", "-")
    memory_dir = os.path.join(home, ".claude/projects", project_key, "memory")
    if os.path.isdir(memory_dir):
        return memory_dir
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Analyze KB access patterns")
    parser.add_argument(
        "--top-topics", action="store_true", help="Show top topics by session count"
    )
    parser.add_argument(
        "--candidates", action="store_true", help="Show skill candidates"
    )
    parser.add_argument(
        "--health", action="store_true", help="Show skill health issues"
    )
    parser.add_argument(
        "--format", choices=["json", "context"], default="json",
        help="Output format (default: json)"
    )
    args = parser.parse_args(argv)

    # Default to all if nothing specified
    if not any([args.top_topics, args.candidates, args.health]):
        args.top_topics = True
        args.candidates = True
        args.health = True

    cwd = os.getcwd()
    result = analyze(
        cwd,
        include_top=args.top_topics,
        include_candidates=args.candidates,
        include_health=args.health,
    )

    if args.format == "context":
        output = format_context(result)
        if output:
            print(output)
    else:
        print(format_json(result))

    return 0


if __name__ == "__main__":
    sys.exit(main())
