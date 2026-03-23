#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""suggestion.py — File-based suggestion pipeline for read-only (global) KBs.

Creates, lists, and formats suggestions in ~/.claude/knowledge-base/suggestions/.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


_SUGGESTIONS_DIR = "~/.claude/knowledge-base/suggestions"


def _resolve_home(path: str) -> Path:
    if path.startswith("~/"):
        return Path.home() / path[2:]
    return Path(path)


def _suggestions_dir() -> Path:
    return _resolve_home(_SUGGESTIONS_DIR)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def create_suggestion(
    target_kb: str,
    target_path: str,
    topic: str,
    action: str,
    reason: str,
    content: str,
    source_project: str | None = None,
) -> Path:
    """Create a suggestion file. Returns the path to the created file."""
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d-%H%M%S")
    slug = _slugify(topic)
    filename = f"{timestamp}-{slug}.md"

    d = _suggestions_dir()
    d.mkdir(parents=True, exist_ok=True)

    source = source_project or str(Path.cwd())
    frontmatter = (
        f"---\n"
        f"target_kb: {target_kb}\n"
        f"target_path: {target_path}\n"
        f"topic: {topic}\n"
        f"action: {action}\n"
        f'reason: "{reason}"\n'
        f"source_project: {source}\n"
        f"created: {now.isoformat()}\n"
        f"status: pending\n"
        f"---\n\n"
    )

    path = d / filename
    path.write_text(frontmatter + content, encoding="utf-8")
    return path


def list_suggestions(status_filter: str | None = None) -> list[dict]:
    """List suggestion files, optionally filtered by status."""
    d = _suggestions_dir()
    if not d.exists():
        return []

    results = []
    for p in sorted(d.glob("*.md"), reverse=True):
        text = p.read_text(encoding="utf-8")
        meta = _parse_frontmatter(text)
        if status_filter and meta.get("status") != status_filter:
            continue
        meta["file"] = str(p)
        results.append(meta)
    return results


def format_suggestion(path: str) -> str:
    """Pretty-print a suggestion file."""
    text = Path(path).read_text(encoding="utf-8")
    meta = _parse_frontmatter(text)
    body = _strip_frontmatter(text)

    lines = [
        f"## Suggestion: {meta.get('topic', '?')}",
        f"**Target**: {meta.get('target_kb', '?')} ({meta.get('target_path', '?')})",
        f"**Action**: {meta.get('action', '?')}",
        f"**Reason**: {meta.get('reason', '?')}",
        f"**From**: {meta.get('source_project', '?')}",
        f"**Created**: {meta.get('created', '?')}",
        f"**Status**: {meta.get('status', '?')}",
        "",
        "### Content",
        body.strip(),
    ]
    return "\n".join(lines)


def _parse_frontmatter(text: str) -> dict:
    meta: dict[str, str] = {}
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return meta
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^(\w[\w-]*):\s*(.+)", line)
        if m:
            meta[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return meta


def _strip_frontmatter(text: str) -> str:
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return text
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            return "\n".join(lines[i + 1:])
    return text


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Manage KB suggestions")
    sub = parser.add_subparsers(dest="command")

    create_p = sub.add_parser("create", help="Create a suggestion")
    create_p.add_argument("--target-kb", required=True)
    create_p.add_argument("--target-path", required=True)
    create_p.add_argument("--topic", required=True)
    create_p.add_argument("--action", choices=["create", "update", "append"], required=True)
    create_p.add_argument("--reason", required=True)
    create_p.add_argument("--content", required=True, help="Content or path to file with content (use @file)")

    list_p = sub.add_parser("list", help="List suggestions")
    list_p.add_argument("--status", choices=["pending", "applied", "rejected"])
    list_p.add_argument("--json", action="store_true")

    show_p = sub.add_parser("show", help="Show a suggestion")
    show_p.add_argument("path", help="Path to suggestion file")

    args = parser.parse_args(argv)

    if args.command == "create":
        content = args.content
        if content.startswith("@"):
            content = Path(content[1:]).read_text(encoding="utf-8")
        path = create_suggestion(
            target_kb=args.target_kb,
            target_path=args.target_path,
            topic=args.topic,
            action=args.action,
            reason=args.reason,
            content=content,
        )
        print(f"Created: {path}")
    elif args.command == "list":
        items = list_suggestions(status_filter=args.status)
        if args.json:
            print(json.dumps(items, indent=2))
        else:
            if not items:
                print("No suggestions found.")
            for item in items:
                status = item.get("status", "?")
                topic = item.get("topic", "?")
                target = item.get("target_kb", "?")
                print(f"  [{status}] {target}/{topic} — {item.get('file', '')}")
    elif args.command == "show":
        print(format_suggestion(args.path))
    else:
        parser.print_help()
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
