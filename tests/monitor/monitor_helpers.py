"""Shared test helpers for kb-monitor scripts."""

import json
import os
from pathlib import Path

def setup_kb_config(tmp_path: Path, kb_roots: list[dict] | None = None) -> Path:
    """Create .claude/knowledge-base/config.json in tmp_path."""
    if kb_roots is None:
        kb_roots = [{"name": "core", "path": "./knowledge"}]
    config_dir = tmp_path / ".claude" / "knowledge-base"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.json"
    config_file.write_text(json.dumps({"kb_roots": kb_roots}))
    return config_file

def setup_access_log(tmp_path: Path, entries: list[dict]) -> Path:
    """Create .claude/knowledge-base/access-log.jsonl in tmp_path."""
    log_dir = tmp_path / ".claude" / "knowledge-base"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "access-log.jsonl"
    lines = [json.dumps(e) for e in entries]
    log_file.write_text("\n".join(lines) + ("\n" if lines else ""))
    return log_file

def setup_memory_dir(tmp_path: Path, content: str = "") -> Path:
    """Create a memory directory with monitoring_kb_observations.md inside tmp_path."""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    if content:
        memory_file = memory_dir / "monitoring_kb_observations.md"
        memory_file.write_text(content)
    return memory_dir

def setup_topic_with_skill(tmp_path: Path, topic: str) -> Path:
    """Create a KB topic that has a skill/ folder."""
    skill_dir = tmp_path / "knowledge" / topic / "skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    return skill_dir

def setup_topic_without_skill(tmp_path: Path, topic: str) -> Path:
    """Create a KB topic without a skill/ folder."""
    topic_dir = tmp_path / "knowledge" / topic
    topic_dir.mkdir(parents=True, exist_ok=True)
    index_file = topic_dir / "index.md"
    index_file.write_text(f"---\nname: {topic}\ndescription: Test.\n---\n")
    return topic_dir

def make_log_entry(
    topic: str,
    sid: str = "abc12345",
    ts: str = "2026-03-14T10:00:00",
    path: str = "",
    kind: str = "kb",
) -> dict:
    """Create an access log entry dict."""
    if not path:
        path = f"knowledge/{topic}/index.md"
    entry = {"ts": ts, "sid": sid, "topic": topic, "path": path}
    if kind != "kb":
        entry["kind"] = kind
    return entry

def setup_global_config(
    tmp_path: Path, source_path: str, namespace: str = "god"
) -> Path:
    """Create a mock global KB config at {tmp_path}/.claude/knowledge-base/config.json."""
    config_dir = tmp_path / ".claude" / "knowledge-base"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.json"
    config_file.write_text(json.dumps({
        "namespace": namespace,
        "source": source_path,
    }))
    return config_file

def setup_global_access_log(tmp_path: Path, entries: list[dict]) -> Path:
    """Create a shared global access log at {tmp_path}/.claude/knowledge-base/access-log.jsonl."""
    log_dir = tmp_path / ".claude" / "knowledge-base"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "access-log.jsonl"
    lines = [json.dumps(e) for e in entries]
    log_file.write_text("\n".join(lines) + ("\n" if lines else ""))
    return log_file

def make_global_log_entry(
    topic: str,
    sid: str = "abc12345",
    ts: str = "2026-03-14T10:00:00",
    path: str = "",
    source_project: str = "project-a",
) -> dict:
    """Create a global access log entry dict with source_project field."""
    if not path:
        path = f"{topic}/index.md"
    return {
        "ts": ts, "sid": sid, "topic": topic,
        "path": path, "source_project": source_project,
    }


MEMORY_WITH_GATES = """\
---
name: kb-monitoring-observations
description: Cross-session KB access patterns
type: project
---

# KB Monitoring Observations

## Skill Candidates
| KB Topic | First Seen | Sessions | Status |
|----------|-----------|----------|--------|

## Skill Health
| Skill | Corrections (30d) | Last Issue | Status |
|-------|-------------------|------------|--------|
| /writing-article | 3 | tone too aggressive (2026-03-10) | action |
| /kb-find | 1 | slow on large KBs (2026-03-12) | watch |

## Conversion History
| Topic | Converted | Skill Name |
|-------|-----------|------------|

## Policy Gates
| Topic/Skill | Gate Type | Condition | Set On |
|-------------|-----------|-----------|--------|
| excluded-topic/ | exclude | permanent — user excluded | 2026-03-13 |
| cooldown-topic/ | cooldown | wait 5 more sessions | 2026-03-10 |
| condition-topic/ | condition | don't fix until X is done | 2026-03-12 |
| * (global) | throttle | max 1 conversion suggestion per session | — |
"""

MEMORY_EMPTY = """\
---
name: kb-monitoring-observations
description: Cross-session KB access patterns
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
"""
