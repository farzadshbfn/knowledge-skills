#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""resolve_skill_paths.py — Resolve KB skill script paths.

Checks project-local (.claude/skills/) then user-global (~/.claude/skills/).
Outputs JSON with resolved paths grouped by purpose:
- validation (required — exit 1 if not found)
- monitoring (optional — null paths if kb-monitor not installed)
"""

import json
import sys
from pathlib import Path


def find_skills_location(project_root: Path) -> Path | None:
    """Return the first .claude/skills/ directory that contains kb-learn."""
    candidates = [
        project_root / ".claude" / "skills",
        Path.home() / ".claude" / "skills",
    ]
    for candidate in candidates:
        if candidate.is_dir() and (candidate / "kb-learn").exists():
            return candidate
    return None


def _resolve(skills_dir: Path, rel_path: str) -> str | None:
    script = skills_dir / rel_path
    return str(script.resolve()) if script.exists() else None


def main(project_root: Path | None = None) -> dict | None:
    """Returns script paths or None if kb-learn is missing."""
    if project_root is None:
        project_root = Path.cwd()

    skills_dir = find_skills_location(project_root)
    if skills_dir is None:
        return None

    validation = _resolve(skills_dir, "kb-learn/scripts/validate_kb.py")
    if validation is None:
        return None

    return {
        "skills_dir": str(skills_dir),
        "validation": validation,
        "monitoring": {
            "track_kb_access": _resolve(skills_dir, "kb-monitor/scripts/track_kb_access.py"),
            "analyze_access": _resolve(skills_dir, "kb-monitor/scripts/analyze_access.py"),
        },
    }


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    result = main(root)
    if result is None:
        print(json.dumps({"error": "kb-learn not found — KB skills are not installed"}))
        sys.exit(1)
    print(json.dumps(result, indent=2))
