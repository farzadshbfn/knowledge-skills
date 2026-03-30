#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""track_kb_access.py — Async PostToolUse hook: logs KB file reads to JSONL.

Receives stdin JSON from Claude Code's PostToolUse hook event (Read tool).
Logs reads of knowledge/ files to .claude/knowledge-base/access-log.jsonl.
Trims entries older than 30 days. Checks in-session threshold for mid-conversation
recommendations via systemMessage output.
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


LOG_DIR = ".claude/knowledge-base"
LOG_FILE = f"{LOG_DIR}/access-log.jsonl"
GLOBAL_LOG_DIR = os.path.join(os.path.expanduser("~"), ".claude/knowledge-base")
GLOBAL_LOG_FILE = os.path.join(GLOBAL_LOG_DIR, "access-log.jsonl")
MAX_AGE_DAYS = 30
IN_SESSION_THRESHOLD_KB = 3
IN_SESSION_THRESHOLD_CODE = 5

# Directories to skip for code tracking (noisy / generated / vendored)
_SKIP_PREFIXES = (
    ".", "node_modules", ".venv", "venv", "__pycache__",
    "build", "dist", ".build", "DerivedData",
)


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return 0

    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    session_id = data.get("session_id", "")
    cwd = data.get("cwd", os.getcwd())

    if not file_path:
        return 0

    # Resolve to relative path from project root
    try:
        rel_path = os.path.relpath(file_path, cwd)
    except ValueError:
        return 0

    # Determine what kind of read this is: KB topic, global KB, or code module
    topic = extract_topic(rel_path, cwd)
    kind = "kb"
    if not topic:
        # Check global KB before code module (global paths start with "..")
        if rel_path.startswith(".."):
            global_result = detect_global_kb_topic(file_path)
            if global_result:
                global_topic, global_rel = global_result
                sid = session_id[:8] if session_id else ""
                log_global_kb_read(global_topic, global_rel, sid, cwd)
                return 0
        topic = extract_code_module(rel_path, cwd)
        kind = "code"
    if not topic:
        return 0

    # Ensure log directory exists
    log_dir = os.path.join(cwd, LOG_DIR)
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(cwd, LOG_FILE)

    # Append entry (KB entries omit 'kind' for backwards compatibility)
    sid = session_id[:8] if session_id else ""
    entry = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "sid": sid,
        "topic": topic,
        "path": rel_path,
    }
    if kind == "code":
        entry["kind"] = "code"
    with open(log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")

    # Trim old entries (periodic — only when file > 1000 lines)
    trim_old_entries(log_file)

    # Mid-conversation threshold check
    check_mid_session(log_file, sid, topic, cwd, kind=kind)

    return 0


def _resolve_home(path: str) -> str:
    """Resolve ~ prefix in a path."""
    if path.startswith("~/"):
        return os.path.join(os.path.expanduser("~"), path[2:])
    return path


def detect_global_kb_topic(abs_path: str) -> tuple[str, str] | None:
    """Check if abs_path is under a global KB root.

    Returns (topic_name, rel_path_within_kb_root) or None.
    """
    global_config_path = os.path.join(
        os.path.expanduser("~"), ".claude/knowledge-base/config.json"
    )
    try:
        with open(global_config_path) as f:
            global_config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

    source = global_config.get("source", "")
    if not source:
        return None
    source = _resolve_home(source)

    source_config_path = os.path.join(source, ".claude/knowledge-base/config.json")
    try:
        with open(source_config_path) as f:
            source_config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

    norm_abs = os.path.realpath(abs_path)
    for entry in source_config.get("kb_roots", []):
        kb_path = entry["path"]
        if kb_path.startswith("./"):
            kb_path = os.path.join(source, kb_path[2:])
        elif not kb_path.startswith("/"):
            kb_path = os.path.join(source, kb_path)
        kb_path = os.path.realpath(kb_path)

        if norm_abs.startswith(kb_path + "/"):
            rel = norm_abs[len(kb_path) + 1:]
            parts = rel.split("/")
            if len(parts) >= 2:
                return (parts[0], rel)
    return None


def log_global_kb_read(
    topic: str, rel_path: str, sid: str, cwd: str
) -> None:
    """Append a read entry to the shared global KB access log."""
    os.makedirs(GLOBAL_LOG_DIR, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "sid": sid,
        "topic": topic,
        "path": rel_path,
        "source_project": os.path.basename(cwd),
    }
    with open(GLOBAL_LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    trim_old_entries(GLOBAL_LOG_FILE)


def extract_topic(rel_path: str, cwd: str) -> str | None:
    """Extract KB topic name from a relative file path. Returns None if not a KB file."""
    # Load KB config for accurate path checking
    config_path = os.path.join(cwd, ".claude/knowledge-base/config.json")
    try:
        with open(config_path) as f:
            config = json.load(f)
        kb_roots = [e["path"].lstrip("./") for e in config.get("kb_roots", [])]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        kb_roots = ["knowledge"]

    for root in kb_roots:
        prefix = f"{root}/"
        if rel_path.startswith(prefix):
            after = rel_path[len(prefix):]
            parts = after.split("/")
            if not parts or not parts[0]:
                return None
            # Root-level non-topic files (CHANGELOG.md, etc.)
            if len(parts) == 1:
                return None
            return parts[0]
    return None


def extract_code_module(rel_path: str, cwd: str) -> str | None:
    """Extract the immediate parent directory from a non-KB file path.

    Returns None for root-level files, dotfiles/dirs, and noisy directories.
    """
    if rel_path.startswith(".."):
        return None

    parts = Path(rel_path).parts
    if len(parts) < 2:
        return None

    # Skip dotfile dirs and noisy/generated dirs
    if parts[0].startswith(".") or parts[0] in _SKIP_PREFIXES:
        return None

    # Also check if it's a KB path (already handled by extract_topic)
    config_path = os.path.join(cwd, ".claude/knowledge-base/config.json")
    try:
        with open(config_path) as f:
            config = json.load(f)
        kb_roots = [e["path"].lstrip("./") for e in config.get("kb_roots", [])]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        kb_roots = ["knowledge"]

    for root in kb_roots:
        if rel_path.startswith(f"{root}/"):
            return None

    # Return the immediate parent directory
    return str(Path(rel_path).parent)


def trim_old_entries(log_file: str) -> None:
    """Remove entries older than MAX_AGE_DAYS. Only runs when file exceeds 1000 lines."""
    try:
        with open(log_file) as f:
            lines = f.readlines()
    except FileNotFoundError:
        return

    if len(lines) < 1000:
        return

    cutoff = (datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    kept = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            if entry.get("ts", "") >= cutoff:
                kept.append(line)
        except json.JSONDecodeError:
            continue

    with open(log_file, "w") as f:
        f.write("\n".join(kept) + ("\n" if kept else ""))


def find_code_cluster(
    entries: list[dict],
    sid: str | None = None,
    base: int = IN_SESSION_THRESHOLD_CODE,
    penalty: int = 3,
) -> tuple[str, int] | None:
    """Find the deepest directory cluster crossing its spread-scaled threshold.

    For each ancestor directory, the threshold grows with the number of unique
    subdirectories contributing reads:  threshold = base + (n_children - 1) * penalty

    Returns (directory, read_count) for the deepest qualifying dir, or None.
    """
    # Filter to code entries for this session
    code_entries = []
    for e in entries:
        if e.get("kind") != "code":
            continue
        if sid is not None and e.get("sid") != sid:
            continue
        code_entries.append(e)

    if not code_entries:
        return None

    # Accumulate subtree reads and unique children per ancestor
    subtree_reads: dict[str, int] = defaultdict(int)
    children: dict[str, set[str]] = defaultdict(set)

    for e in code_entries:
        topic = e["topic"]  # immediate parent dir of the file
        subtree_reads[topic] += 1

        # Bubble up: each ancestor gets the read, and tracks which child contributed
        parts = Path(topic).parts
        for i in range(len(parts) - 1, 0, -1):
            ancestor = str(Path(*parts[:i]))
            child_name = parts[i]
            subtree_reads[ancestor] += 1
            children[ancestor].add(child_name)

    # Find directories that cross their threshold
    candidates = []
    for d, reads in subtree_reads.items():
        n_children = len(children.get(d, set()))
        effective_threshold = base + max(0, n_children - 1) * penalty
        if reads >= effective_threshold:
            candidates.append((d, reads, len(Path(d).parts)))

    if not candidates:
        return None

    # Deepest wins (most path components)
    candidates.sort(key=lambda c: c[2], reverse=True)
    return (candidates[0][0], candidates[0][1])


def check_mid_session(
    log_file: str, sid: str, current_topic: str, cwd: str, kind: str = "kb"
) -> None:
    """Check if in-session threshold is crossed for a topic or code module."""
    if not sid:
        return

    # Load all entries from the log
    try:
        with open(log_file) as f:
            lines = f.readlines()
    except FileNotFoundError:
        return

    entries = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if kind == "code":
        # Use cluster analysis for code reads
        result = find_code_cluster(entries, sid=sid)
        if result is None:
            return
        cluster_dir, count = result

        # Check marker for this cluster
        safe_topic = cluster_dir.replace("/", "_")
        marker = os.path.join(cwd, LOG_DIR, f".emitted-{sid}-{safe_topic}")
        if os.path.exists(marker):
            return

        msg = {
            "systemMessage": (
                f"[kb-monitor] You've read {cluster_dir}/ "
                f"{count} times this session. This code area might benefit "
                f"from a skill to capture its patterns and usage."
            )
        }
        print(json.dumps(msg))

        try:
            Path(marker).touch()
        except OSError:
            pass
    else:
        # KB: simple count-based threshold
        count = sum(
            1 for e in entries
            if e.get("sid") == sid and e.get("topic") == current_topic
        )
        if count < IN_SESSION_THRESHOLD_KB:
            return

        if topic_has_skill(current_topic, cwd):
            return
        if is_gated(current_topic, cwd):
            return

        safe_topic = current_topic.replace("/", "_")
        marker = os.path.join(cwd, LOG_DIR, f".emitted-{sid}-{safe_topic}")
        if os.path.exists(marker):
            return

        msg = {
            "systemMessage": (
                f"[kb-monitor] You've read {current_topic}/ "
                f"{count} times this session and it has no skill. "
                f"Consider /kb-monitor --convert {current_topic}/."
            )
        }
        print(json.dumps(msg))

        try:
            Path(marker).touch()
        except OSError:
            pass


def topic_has_skill(topic: str, cwd: str) -> bool:
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


def is_gated(topic: str, cwd: str) -> bool:
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
        # Check for topic-specific gate
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


if __name__ == "__main__":
    sys.exit(main())
