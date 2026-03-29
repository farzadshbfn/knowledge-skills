#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""validate_kb.py — Validate knowledge base integrity.

Checks: frontmatter (per file type), broken links, wikilinks, orphans, note size, TOC.
All logic in pure functions; CLI entry point at __main__.
"""

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class KBEntry:
    name: str          # e.g. "core", "ios"
    path: str          # e.g. "./knowledge"
    readonly: bool = False


@dataclass
class KBConfig:
    entries: list[KBEntry]
    namespace: str = ""


@dataclass
class Issue:
    level: str       # "error" | "warning"
    check: str       # e.g. "broken_link", "missing_field"
    file: str        # relative path
    message: str
    detail: str = ""


@dataclass
class Stats:
    total_notes: int = 0
    topic_notes: int = 0
    index_notes: int = 0
    skill_files: int = 0
    agent_files: int = 0
    reference_files: int = 0
    asset_files: int = 0
    total_links: int = 0


@dataclass
class ValidationResult:
    issues: list[Issue] = field(default_factory=list)
    stats: Stats = field(default_factory=Stats)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]

    def to_dict(self) -> dict:
        def _issue(i: Issue) -> dict:
            return {"check": i.check, "file": i.file, "message": i.message, "detail": i.detail}
        from dataclasses import asdict
        return {
            "errors": [_issue(i) for i in self.errors],
            "warnings": [_issue(i) for i in self.warnings],
            "stats": asdict(self.stats),
        }


# File classification

TOPIC = "topic"
INDEX = "index"
SKILL = "skill"
PROJECT_AGENT = "project_agent"
SKILL_AGENT = "skill_agent"
REFERENCE = "reference"
ASSET = "asset"
UNKNOWN = "unknown"


def classify_file(rel_path: str) -> str:
    """Classify a markdown file by its path relative to project root."""
    parts = Path(rel_path).parts
    name = Path(rel_path).name

    if len(parts) >= 3 and parts[0] == ".claude" and parts[1] == "agents":
        return PROJECT_AGENT

    if "skill" in parts:
        skill_idx = list(parts).index("skill")
        after_skill = parts[skill_idx + 1:] if skill_idx + 1 < len(parts) else ()

        if name == "SKILL.md":
            return SKILL
        if after_skill and after_skill[0] == "agents":
            return SKILL_AGENT
        if after_skill and after_skill[0] == "assets":
            return ASSET
        if after_skill and after_skill[0].startswith("reference"):
            return REFERENCE
        return UNKNOWN

    if "assets" in parts:
        return ASSET

    if any(p.startswith(".") for p in parts):
        return UNKNOWN

    if name == "CHANGELOG.md":
        return UNKNOWN

    if name == "index.md" or name.endswith("-index.md"):
        return INDEX
    return TOPIC


# Frontmatter parsing

def parse_frontmatter(content: str) -> tuple[dict | None, int]:
    """Return (fields_dict, body_start_line) or (None, 0) if no frontmatter."""
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, 0

    end_idx = None
    for i in range(1, min(len(lines), 50)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return None, 0

    fm: dict = {}
    current_key: str | None = None
    current_list: list | None = None

    for line in lines[1:end_idx]:
        if current_list is not None and line.strip().startswith("- "):
            current_list.append(line.strip()[2:].strip().strip('"').strip("'"))
            continue
        elif current_list is not None:
            fm[current_key] = current_list
            current_list = None

        m = re.match(r"^([\w][\w-]*):\s*(.*)", line)
        if not m:
            continue
        key = m.group(1)
        value = m.group(2).strip()
        current_key = key

        if not value:
            current_list = []
            continue

        if value.startswith("[") and value.endswith("]"):
            items = value[1:-1].split(",")
            fm[key] = [it.strip().strip('"').strip("'") for it in items if it.strip()]
        elif value.lower() in ("true", "false"):
            fm[key] = value.lower() == "true"
        elif re.fullmatch(r"\d+", value):
            fm[key] = int(value)
        else:
            fm[key] = value.strip('"').strip("'")

    if current_list is not None and current_key is not None:
        fm[current_key] = current_list

    return fm, end_idx + 1


# Frontmatter validation rules

REQUIRED_FIELDS: dict[str, list[str]] = {
    TOPIC:       ["name", "description"],
    INDEX:         ["name", "description"],
    SKILL:         ["name", "description"],
    PROJECT_AGENT: ["name", "description"],
    SKILL_AGENT:   ["name", "description", "tools", "model"],
}

OPTIONAL_FIELDS: dict[str, list[str]] = {
    TOPIC:       [],
    INDEX:         [],
    SKILL:         ["argument-hint", "user-invocable", "hooks", "effort"],
    PROJECT_AGENT: ["tools", "model", "skills", "hooks", "effort"],
    SKILL_AGENT:   ["background", "skills", "hooks", "effort"],
}

ALLOWED_MODELS = {"haiku", "sonnet", "opus"}
ALLOWED_EFFORTS = {"low", "medium", "high", "max"}


def validate_frontmatter(
    fm: dict | None,
    file_type: str,
    rel_path: str,
) -> list[Issue]:
    """Return issues for frontmatter validation."""
    issues: list[Issue] = []

    if file_type in (REFERENCE, ASSET, UNKNOWN):
        return issues

    if fm is None:
        issues.append(Issue("error", "frontmatter_missing", rel_path, "Missing frontmatter block"))
        return issues

    for fname in REQUIRED_FIELDS.get(file_type, []):
        if fname not in fm:
            issues.append(Issue("error", "missing_field", rel_path, f"Missing required field: {fname}"))
        elif isinstance(fm[fname], str) and not fm[fname].strip():
            issues.append(Issue("error", "empty_field", rel_path, f"Empty required field: {fname}"))

    if file_type in (PROJECT_AGENT, SKILL_AGENT):
        if "model" in fm and isinstance(fm["model"], str):
            normalised = fm["model"].replace("claude-", "")
            if normalised not in ALLOWED_MODELS:
                issues.append(Issue("warning", "unknown_model", rel_path,
                                    f"Unknown model: {fm['model']} (expected {', '.join(sorted(ALLOWED_MODELS))})"))
        if "background" in fm and not isinstance(fm["background"], bool):
            issues.append(Issue("warning", "invalid_background", rel_path,
                                f"background should be boolean, got {type(fm['background']).__name__}"))
        if "skills" in fm and not isinstance(fm["skills"], list):
            issues.append(Issue("warning", "invalid_skills", rel_path,
                                f"skills should be a list, got {type(fm['skills']).__name__}"))

    if file_type in (SKILL, PROJECT_AGENT, SKILL_AGENT):
        if "effort" in fm and fm["effort"] not in ALLOWED_EFFORTS:
            issues.append(Issue("warning", "invalid_effort", rel_path,
                                f"Invalid effort: {fm['effort']} (expected {', '.join(sorted(ALLOWED_EFFORTS))})"))

    allowed = set(REQUIRED_FIELDS.get(file_type, []) + OPTIONAL_FIELDS.get(file_type, []))
    if allowed:
        for key in fm:
            if key not in allowed:
                issues.append(Issue("warning", "unexpected_field", rel_path,
                                    f"Unexpected frontmatter field: {key}"))

    return issues


# Link helpers

def extract_md_links(content: str) -> list[tuple[int, str]]:
    """Return [(line_number, target_path)] for .md links, skipping code blocks."""
    links: list[tuple[int, str]] = []
    in_fenced = False

    for line_num, line in enumerate(content.split("\n"), 1):
        if line.strip().startswith("```"):
            in_fenced = not in_fenced
            continue
        if in_fenced:
            continue
        cleaned = re.sub(r"`[^`]*`", "", line)
        for m in re.finditer(r"\[((?:[^\[\]]|\[[^\]]*\])*)\]\(([^)]+\.md)\)", cleaned):
            links.append((line_num, m.group(2)))

    return links


def normalize_path(base_dir: str, link: str) -> str:
    """Resolve link relative to base_dir (no I/O)."""
    if link.startswith("/"):
        segments = link.strip("/").split("/")
    else:
        segments = (base_dir + "/" + link).split("/")

    stack: list[str] = []
    for seg in segments:
        if seg == "..":
            if stack:
                stack.pop()
        elif seg and seg != ".":
            stack.append(seg)
    return "/".join(stack)


# Validation checks

def check_broken_links(
    files: dict[str, str],
    check_scope: set[str] | None = None,
) -> list[Issue]:
    """Check for broken internal markdown links."""
    issues: list[Issue] = []
    file_set = set(files.keys())
    scope = check_scope if check_scope is not None else file_set

    for rel_path in scope:
        content = files.get(rel_path, "")
        file_dir = str(Path(rel_path).parent)

        for line_num, link in extract_md_links(content):
            if link.startswith("@"):
                continue
            target = normalize_path(file_dir, link)
            if target not in file_set:
                issues.append(Issue(
                    "error", "broken_link", rel_path,
                    f"Broken link: {link}",
                    f"line {line_num}, resolved to: {target}",
                ))

    return issues


def check_wikilinks(
    files: dict[str, str],
    check_scope: set[str] | None = None,
) -> list[Issue]:
    """Detect [[wikilinks]] (not allowed)."""
    issues: list[Issue] = []
    scope = check_scope if check_scope is not None else set(files.keys())

    for rel_path in scope:
        content = files.get(rel_path, "")
        in_fenced = False
        for line_num, line in enumerate(content.split("\n"), 1):
            if line.strip().startswith("```"):
                in_fenced = not in_fenced
                continue
            if in_fenced:
                continue
            cleaned = re.sub(r"`[^`]*`", "", line)
            for m in re.finditer(r"\[\[[^\]]+\]\]", cleaned):
                issues.append(Issue(
                    "error", "wikilink", rel_path,
                    f"Wikilink found: {m.group()}",
                    f"line {line_num}",
                ))

    return issues


def check_orphans(
    files: dict[str, str],
) -> list[Issue]:
    """Find topic notes not referenced by any other file."""
    issues: list[Issue] = []

    topic_files: set[str] = set()
    for rel_path in files:
        if Path(rel_path).name == "CHANGELOG.md":
            continue
        if any(p.startswith(".") for p in Path(rel_path).parts):
            continue
        # Inside skill folders: include reference/ and agents/, skip assets/ and SKILL.md
        if "/skill/" in rel_path:
            parts = Path(rel_path).parts
            skill_idx = list(parts).index("skill")
            sub = parts[skill_idx + 1] if skill_idx + 1 < len(parts) else ""
            if sub == "assets" or Path(rel_path).name == "SKILL.md":
                continue
            # scripts/ and other non-md infrastructure — skip
            if sub not in ("reference", "agents"):
                continue
        topic_files.add(rel_path)

    topic_files.discard("index.md")

    referenced: set[str] = set()
    for rel_path, content in files.items():
        file_dir = str(Path(rel_path).parent)
        for _, link in extract_md_links(content):
            referenced.add(normalize_path(file_dir, link))

    for cf in sorted(topic_files):
        if cf not in referenced:
            bname = Path(cf).name
            if not any(ref.endswith("/" + bname) or ref == bname for ref in referenced):
                issues.append(Issue("warning", "orphan_note", cf, "Not referenced by any other file"))

    return issues


def check_note_sizes(files: dict[str, str], max_lines: int = 500) -> list[Issue]:
    """Flag notes exceeding *max_lines*. CHANGELOG.md is exempt."""
    issues: list[Issue] = []
    for rel_path, content in files.items():
        if Path(rel_path).name == "CHANGELOG.md":
            continue
        n = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        if n > max_lines:
            issues.append(Issue("warning", "oversized_note", rel_path, f"{n} lines (limit {max_lines})"))
    return issues


def check_toc(
    files: dict[str, str],
    min_lines: int = 100,
    check_scope: set[str] | None = None,
) -> list[Issue]:
    """Long notes must have ## Contents near the top."""
    issues: list[Issue] = []
    scope = check_scope if check_scope is not None else set(files.keys())

    for rel_path in scope:
        content = files.get(rel_path, "")
        lines = content.split("\n")
        if len(lines) <= min_lines:
            continue

        # Find body start (skip frontmatter)
        body_start = 0
        if lines and lines[0].strip() == "---":
            for i in range(1, min(len(lines), 50)):
                if lines[i].strip() == "---":
                    body_start = i + 1
                    break

        first_ten = "\n".join(lines[body_start : body_start + 10])
        if "## Contents" not in first_ten:
            issues.append(Issue(
                "warning", "missing_toc", rel_path,
                f"{len(lines)} lines but no '## Contents' in first 10 lines of body",
            ))

    return issues


def check_skill_exclusivity(files: dict[str, str]) -> list[Issue]:
    """Topic folders with a skill/ subfolder must have only index.md outside skill/."""
    issues: list[Issue] = []

    skill_topic_folders: set[str] = set()
    for rel_path in files:
        parts = Path(rel_path).parts
        if len(parts) >= 2 and "skill" in parts:
            skill_idx = list(parts).index("skill")
            topic_folder = "/".join(parts[:skill_idx])
            skill_topic_folders.add(topic_folder)

    for folder in sorted(skill_topic_folders):
        for rel_path in sorted(files):
            if not rel_path.startswith(folder + "/"):
                continue
            remaining = rel_path[len(folder) + 1:]
            if "/" in remaining:
                continue
            if Path(rel_path).name == "index.md":
                continue
            issues.append(Issue(
                "error", "skill_exclusivity", rel_path,
                "this file either needs to be removed or moved into skill folder "
                "as a reference or asset or dissolved into index",
            ))

    return issues


def check_skill_scope(files: dict[str, str]) -> list[Issue]:
    """Files inside skill/ folders must not link to files outside their skill/ folder."""
    issues: list[Issue] = []

    for rel_path in sorted(files):
        parts = Path(rel_path).parts
        if "skill" not in parts:
            continue
        skill_idx = list(parts).index("skill")
        after_skill = parts[skill_idx + 1:] if skill_idx + 1 < len(parts) else ()
        if after_skill and after_skill[0] == "assets":
            continue

        skill_prefix = "/".join(parts[:skill_idx + 1]) + "/"
        content = files[rel_path]
        file_dir = str(Path(rel_path).parent)

        for line_num, link in extract_md_links(content):
            resolved = normalize_path(file_dir, link)
            if not resolved.startswith(skill_prefix):
                issues.append(Issue(
                    "error", "skill_scope", rel_path,
                    "skills cannot have direct links to outside of their folder scope",
                    f"line {line_num}, link: {link}",
                ))

    return issues


def check_missing_index(files: dict[str, str]) -> list[Issue]:
    """Every folder must have an index (or SKILL.md for skill/)."""
    issues: list[Issue] = []

    folders: set[str] = set()
    for rel_path in files:
        if Path(rel_path).name == "CHANGELOG.md":
            continue
        if any(p.startswith(".") for p in Path(rel_path).parts):
            continue
        parent = str(Path(rel_path).parent)
        if parent and parent != ".":
            folders.add(parent)
            folders.add(".")  # include root when subfolders exist
            p = Path(parent).parent
            while str(p) != ".":
                folders.add(str(p))
                p = p.parent

    for folder in sorted(folders):
        parts = Path(folder).parts

        if parts and parts[-1] == "skill":
            if f"{folder}/SKILL.md" not in files:
                issues.append(Issue(
                    "warning", "missing_index", folder,
                    "skill/ folder missing SKILL.md",
                ))
            continue

        if "skill" in parts:
            skill_idx = list(parts).index("skill")
            if skill_idx < len(parts) - 1:
                continue

        if folder == ".":
            prefix = ""
            has_index = "index.md" in files or any(
                Path(f).name.endswith("-index.md")
                for f in files
                if "/" not in f
            )
        else:
            prefix = folder + "/"
            has_index = f"{prefix}index.md" in files or any(
                Path(f).name.endswith("-index.md")
                for f in files
                if f.startswith(prefix) and "/" not in f[len(prefix):]
            )
        if not has_index:
            issues.append(Issue(
                "error", "missing_index", folder,
                "Folder missing index.md",
            ))

    return issues


def check_index_coverage(files: dict[str, str]) -> list[Issue]:
    """Index files must link to all immediate .md siblings and subfolders."""
    issues: list[Issue] = []

    for rel_path, content in files.items():
        if Path(rel_path).name == "CHANGELOG.md":
            continue
        if any(p.startswith(".") for p in Path(rel_path).parts):
            continue

        name = Path(rel_path).name
        is_skill_index = name == "SKILL.md"
        is_index = (
            name == "index.md"
            or name.endswith("-index.md")
            or is_skill_index
        )
        if not is_index:
            continue

        folder = str(Path(rel_path).parent)

        severity = "warning" if is_skill_index else "error"
        file_dir = str(Path(rel_path).parent)
        linked: set[str] = set()
        for _, link in extract_md_links(content):
            if link.startswith("@"):
                continue
            linked.add(normalize_path(file_dir, link))

        is_root = folder == "."
        seen_subfolders: set[str] = set()
        for other in sorted(files):
            if other == rel_path:
                continue
            if Path(other).name == "CHANGELOG.md":
                continue
            if is_root:
                remaining = other
            else:
                if not other.startswith(folder + "/"):
                    continue
                remaining = other[len(folder) + 1:]

            if "/" not in remaining:
                if other not in linked:
                    issues.append(Issue(
                        severity, "index_coverage", rel_path,
                        f"Index missing link to sibling: {Path(other).name}",
                        f"expected link to: {remaining}",
                    ))
            else:
                subfolder_name = remaining.split("/")[0]
                if subfolder_name in seen_subfolders:
                    continue
                seen_subfolders.add(subfolder_name)

                subfolder_path = f"{subfolder_name}" if is_root else f"{folder}/{subfolder_name}"
                if is_skill_index:
                    has_link = any(
                        l.startswith(subfolder_path + "/") for l in linked
                    )
                else:
                    candidates = [
                        f"{subfolder_path}/index.md",
                        f"{subfolder_path}/SKILL.md",
                    ]
                    has_link = any(c in linked for c in candidates)
                if not has_link:
                    issues.append(Issue(
                        severity, "index_coverage", rel_path,
                        f"Index missing link to subfolder: {subfolder_name}/",
                        f"expected link to {subfolder_name}/index.md or SKILL.md",
                    ))

    return issues


def check_changelog(
    changed_files: list[str],
    kb_root: str,
) -> list[Issue]:
    """If .md files under KB root changed, CHANGELOG.md must also be changed."""
    issues: list[Issue] = []
    norm_root = kb_root.lstrip("./")
    kb_prefix = f"{norm_root}/"
    changelog_path = f"{norm_root}/CHANGELOG.md"
    norm_changed = [f.lstrip("./") for f in changed_files]

    has_topic_md = any(
        f.startswith(kb_prefix) and f.endswith(".md") and f != changelog_path
        for f in norm_changed
    )
    if not has_topic_md:
        return issues

    if changelog_path not in norm_changed:
        issues.append(Issue(
            "error", "missing_changelog", changelog_path,
            "KB has changes but CHANGELOG.md was not updated",
        ))

    return issues


_VALID_CONF_TAGS = {"<conf:high>", "<conf:medium>", "<conf:low>"}
_CONF_TAG_RE = re.compile(r"<conf:[^>]*>")


def check_confidence_tags(files: dict[str, str]) -> list[Issue]:
    """Validate inline confidence tags in topic notes."""
    issues: list[Issue] = []
    for rel_path, content in files.items():
        if classify_file(rel_path) != TOPIC:
            continue
        for match in _CONF_TAG_RE.finditer(content):
            tag = match.group(0)
            if tag not in _VALID_CONF_TAGS:
                issues.append(Issue(
                    "error", "invalid_conf_tag", rel_path,
                    f"Malformed confidence tag: {tag}",
                    "valid tags: <conf:high>, <conf:medium>, <conf:low>",
                ))
            elif tag == "<conf:low>":
                issues.append(Issue(
                    "warning", "low_confidence", rel_path,
                    "Low-confidence claim present",
                    f"found {tag} — consider verifying or removing",
                ))
    return issues


# Filesystem protocol (enables mocking)

class FileSystem(Protocol):
    def read_text(self, path: str) -> str: ...
    def exists(self, path: str) -> bool: ...
    def list_md_files(self, root: str) -> list[str]: ...


class RealFileSystem:
    def read_text(self, path: str) -> str:
        return Path(path).read_text(encoding="utf-8")

    def exists(self, path: str) -> bool:
        return Path(path).exists()

    def list_md_files(self, root: str) -> list[str]:
        root_path = Path(root)
        return sorted(
            str(p.relative_to(root_path))
            for p in root_path.rglob("*.md")
            if not any(
                (part.startswith(".") and part != ".claude") or part.startswith("__")
                for part in p.relative_to(root_path).parts
            )
        )


class MockFileSystem:
    """In-memory filesystem for testing."""

    def __init__(self, files: dict[str, str]):
        self._files = files

    def read_text(self, path: str) -> str:
        if path in self._files:
            return self._files[path]
        raise FileNotFoundError(path)

    def exists(self, path: str) -> bool:
        return path in self._files

    def list_md_files(self, root: str) -> list[str]:
        prefix = root.rstrip("/") + "/"
        return sorted(
            p[len(prefix):]
            for p in self._files
            if p.startswith(prefix) and p.endswith(".md")
        )


# Main validation orchestrator

def validate_kb(
    kb_root: str,
    *,
    fs: FileSystem | None = None,
    agent_root: str | None = None,
) -> ValidationResult:
    """Run all validation checks."""
    fs = fs or RealFileSystem()
    result = ValidationResult()

    all_files: dict[str, str] = {}

    for rel_path in fs.list_md_files(kb_root):
        full = f"{kb_root}/{rel_path}"
        try:
            all_files[rel_path] = fs.read_text(full)
        except (OSError, UnicodeDecodeError):
            result.issues.append(Issue("error", "read_error", rel_path, "Could not read file"))

    agent_files_map: dict[str, str] = {}
    if agent_root:
        for rel in fs.list_md_files(agent_root):
            full = f"{agent_root}/{rel}"
            agent_key = f".claude/agents/{rel}"
            try:
                agent_files_map[agent_key] = fs.read_text(full)
            except (OSError, UnicodeDecodeError):
                result.issues.append(Issue("error", "read_error", agent_key, "Could not read file"))

    combined = {**all_files, **agent_files_map}

    topic_scope: set[str] = set()

    for rel_path, content in combined.items():
        fm, _ = parse_frontmatter(content)
        ftype = classify_file(rel_path)

        match ftype:
            case "topic":
                result.stats.topic_notes += 1
                topic_scope.add(rel_path)
            case "index":
                result.stats.index_notes += 1
                topic_scope.add(rel_path)
            case "skill":
                result.stats.skill_files += 1
            case "project_agent" | "skill_agent":
                result.stats.agent_files += 1
            case "reference":
                result.stats.reference_files += 1
            case "asset":
                result.stats.asset_files += 1

        result.issues.extend(validate_frontmatter(fm, ftype, rel_path))

    result.stats.total_notes = len(combined)

    link_scope = {
        p for p in all_files
        if "/assets/" not in p
    }
    result.issues.extend(check_broken_links(all_files, check_scope=link_scope))
    for content in combined.values():
        result.stats.total_links += len(extract_md_links(content))
    result.issues.extend(check_wikilinks(all_files, check_scope=link_scope))
    result.issues.extend(check_orphans(all_files))
    result.issues.extend(check_note_sizes(combined))
    result.issues.extend(check_toc(all_files, check_scope=topic_scope))
    result.issues.extend(check_skill_exclusivity(all_files))
    result.issues.extend(check_skill_scope(all_files))
    result.issues.extend(check_missing_index(all_files))
    result.issues.extend(check_index_coverage(all_files))
    result.issues.extend(check_confidence_tags(all_files))

    return result


# Multi-KB validation

def check_kb_path_exclusivity(config: KBConfig) -> list[Issue]:
    """Validate that no KB path is a prefix of another."""
    issues: list[Issue] = []
    paths = [(e.name, e.path.rstrip("/")) for e in config.entries]
    for i, (name_a, path_a) in enumerate(paths):
        for name_b, path_b in paths[i + 1:]:
            a = path_a.lstrip("./")
            b = path_b.lstrip("./")
            if a.startswith(b + "/") or b.startswith(a + "/") or a == b:
                issues.append(Issue(
                    "error", "nested_kb_paths", f"{name_a}, {name_b}",
                    f"KB paths overlap: '{path_a}' and '{path_b}' — KB paths must be exclusive (no nesting)",
                ))
    return issues


def check_cross_kb_links(
    config: KBConfig,
    kb_file_maps: dict[str, dict[str, str]],
) -> list[Issue]:
    """Validate @kb-name/path links across KBs."""
    issues: list[Issue] = []
    kb_names = {e.name for e in config.entries}

    for kb_name, files in kb_file_maps.items():
        for rel_path, content in files.items():
            for line_num, line in enumerate(content.split("\n"), 1):
                if line.strip().startswith("```"):
                    continue
                cleaned = re.sub(r"`[^`]*`", "", line)
                for m in re.finditer(r"\[([^\]]+)\]\(@([^/]+)/([^)]+\.md)\)", cleaned):
                    target_kb = m.group(2)
                    target_path = m.group(3)
                    if target_kb not in kb_names:
                        issues.append(Issue(
                            "error", "unknown_cross_kb", f"[{kb_name}] {rel_path}",
                            f"Unknown KB reference: @{target_kb}",
                            f"line {line_num}",
                        ))
                    elif target_kb in kb_file_maps:
                        target_files = kb_file_maps[target_kb]
                        if target_path not in target_files:
                            issues.append(Issue(
                                "error", "broken_cross_kb_link", f"[{kb_name}] {rel_path}",
                                f"Broken cross-KB link: @{target_kb}/{target_path}",
                                f"line {line_num}, target not found in KB '{target_kb}'",
                            ))
    return issues


def check_cross_kb_escape(
    config: KBConfig,
    kb_file_maps: dict[str, dict[str, str]],
) -> list[Issue]:
    """Detect relative links that escape one KB and land in another."""
    issues: list[Issue] = []

    kb_paths: dict[str, str] = {}
    for entry in config.entries:
        kb_paths[entry.name] = entry.path.rstrip("/").lstrip("./")

    for kb_name, files in kb_file_maps.items():
        own_prefix = kb_paths[kb_name]
        for rel_path, content in files.items():
            file_dir = str(Path(rel_path).parent)
            full_file_dir = f"{own_prefix}/{file_dir}"

            for line_num, link in extract_md_links(content):
                if link.startswith("@"):
                    continue
                resolved = normalize_path(full_file_dir, link)
                for other_name, other_prefix in kb_paths.items():
                    if other_name == kb_name:
                        continue
                    if resolved.startswith(other_prefix + "/") or resolved == other_prefix:
                        issues.append(Issue(
                            "error", "cross_kb_escape", f"[{kb_name}] {rel_path}",
                            f"Relative link escapes into KB '{other_name}': {link} — use @{other_name}/path instead",
                            f"line {line_num}, resolved to: {resolved}",
                        ))
    return issues


def check_hard_links_to_readonly(
    config: KBConfig,
    kb_file_maps: dict[str, dict[str, str]],
) -> list[Issue]:
    """Reject hard markdown links (not soft `see:` refs) targeting readonly KBs."""
    issues: list[Issue] = []
    readonly_names = {e.name for e in config.entries if e.readonly}
    if not readonly_names:
        return issues

    for kb_name, files in kb_file_maps.items():
        if kb_name in readonly_names:
            continue  # don't check inside readonly KBs themselves
        for rel_path, content in files.items():
            in_code_block = False
            for line_num, line in enumerate(content.split("\n"), 1):
                if line.strip().startswith("```"):
                    in_code_block = not in_code_block
                    continue
                if in_code_block:
                    continue
                cleaned = re.sub(r"`[^`]*`", "", line)
                for m in re.finditer(r"\[([^\]]+)\]\(@([^/]+(?:\.[^/]+)?)/([^)]+)\)", cleaned):
                    target_kb = m.group(2)
                    if target_kb in readonly_names:
                        issues.append(Issue(
                            "error", "hard_link_to_readonly", f"[{kb_name}] {rel_path}",
                            f"Hard markdown link to read-only KB '@{target_kb}' — use soft reference (`see: @{target_kb}/topic`) instead",
                            f"line {line_num}",
                        ))
    return issues


def check_soft_refs(
    config: KBConfig,
    kb_file_maps: dict[str, dict[str, str]],
) -> list[Issue]:
    """Validate `see: @namespace.kb/topic` references point to known KBs."""
    issues: list[Issue] = []
    kb_names = {e.name for e in config.entries}

    for kb_name, files in kb_file_maps.items():
        for rel_path, content in files.items():
            in_code_block = False
            for line_num, line in enumerate(content.split("\n"), 1):
                if line.strip().startswith("```"):
                    in_code_block = not in_code_block
                    continue
                if in_code_block:
                    continue
                cleaned = re.sub(r"`[^`]*`", "", line)
                for m in re.finditer(r"see:\s+@([^\s/]+)/(\S+)", cleaned):
                    ref_kb = m.group(1)
                    if ref_kb not in kb_names:
                        issues.append(Issue(
                            "warning", "unknown_soft_ref", f"[{kb_name}] {rel_path}",
                            f"Soft reference to unknown KB: @{ref_kb}",
                            f"line {line_num}",
                        ))
    return issues


def check_readonly_writes(
    config: KBConfig,
    changed_files: list[str],
) -> list[Issue]:
    """Reject file changes inside read-only KB paths."""
    issues: list[Issue] = []
    from os.path import abspath, commonpath

    for entry in config.entries:
        if not entry.readonly:
            continue
        abs_root = abspath(entry.path)
        for f in changed_files:
            abs_file = abspath(f)
            try:
                if commonpath([abs_file, abs_root]) == abs_root:
                    issues.append(Issue(
                        "error", "readonly_kb_write", f,
                        f"File modified in read-only KB '{entry.name}' — changes to read-only KBs are not allowed",
                    ))
            except ValueError:
                continue
    return issues


def validate_multi_kb(
    config: KBConfig,
    *,
    fs: FileSystem | None = None,
    agent_root: str | None = None,
) -> ValidationResult:
    """Run validation across all configured KBs."""
    fs = fs or RealFileSystem()
    combined = ValidationResult()
    combined.issues.extend(check_kb_path_exclusivity(config))
    if combined.errors:
        return combined

    kb_file_maps: dict[str, dict[str, str]] = {}

    for entry in config.entries:
        # Skip full validation of readonly (global) KBs — only load their files for cross-KB checks
        if entry.readonly:
            all_files: dict[str, str] = {}
            for rel_path in fs.list_md_files(entry.path):
                full = f"{entry.path}/{rel_path}"
                try:
                    all_files[rel_path] = fs.read_text(full)
                except (OSError, UnicodeDecodeError):
                    continue
            kb_file_maps[entry.name] = all_files
            continue

        result = validate_kb(entry.path, fs=fs, agent_root=agent_root)

        for issue in result.issues:
            issue.file = f"[{entry.name}] {issue.file}"
        combined.issues.extend(result.issues)

        combined.stats.total_notes += result.stats.total_notes
        combined.stats.topic_notes += result.stats.topic_notes
        combined.stats.index_notes += result.stats.index_notes
        combined.stats.skill_files += result.stats.skill_files
        combined.stats.agent_files += result.stats.agent_files
        combined.stats.reference_files += result.stats.reference_files
        combined.stats.asset_files += result.stats.asset_files
        combined.stats.total_links += result.stats.total_links

        all_files = {}
        for rel_path in fs.list_md_files(entry.path):
            full = f"{entry.path}/{rel_path}"
            try:
                all_files[rel_path] = fs.read_text(full)
            except (OSError, UnicodeDecodeError):
                continue
        kb_file_maps[entry.name] = all_files

    combined.issues.extend(check_cross_kb_links(config, kb_file_maps))
    combined.issues.extend(check_cross_kb_escape(config, kb_file_maps))
    combined.issues.extend(check_hard_links_to_readonly(config, kb_file_maps))
    combined.issues.extend(check_soft_refs(config, kb_file_maps))

    changed = _get_git_changed_files()
    if changed:
        combined.issues.extend(check_readonly_writes(config, changed))
        for entry in config.entries:
            if not entry.readonly:
                combined.issues.extend(check_changelog(changed, entry.path))

    return combined


# Output formatters

def format_text(result: ValidationResult, *, quiet: bool = False) -> str:
    lines: list[str] = []

    if not quiet:
        lines.append("=== Knowledge Base Validation ===")
        lines.append("")

    if result.errors:
        if not quiet:
            lines.append("## Errors")
        for i in result.errors:
            d = f" ({i.detail})" if i.detail else ""
            lines.append(f"  {i.check}: {i.file} — {i.message}{d}")
        lines.append("")

    if result.warnings:
        if not quiet:
            lines.append("## Warnings")
        for i in result.warnings:
            d = f" ({i.detail})" if i.detail else ""
            lines.append(f"  {i.check}: {i.file} — {i.message}{d}")
        lines.append("")

    if not quiet:
        s = result.stats
        lines.append("## Summary")
        lines.append(f"  Total notes:     {s.total_notes}")
        lines.append(f"  Topic notes:   {s.topic_notes}")
        lines.append(f"  Index notes:     {s.index_notes}")
        lines.append(f"  Skill files:     {s.skill_files}")
        lines.append(f"  Agent files:     {s.agent_files}")
        lines.append(f"  Reference files: {s.reference_files}")
        lines.append(f"  Asset files:     {s.asset_files}")
        lines.append(f"  Total links:     {s.total_links}")
        lines.append(f"  Errors:          {len(result.errors)}")
        lines.append(f"  Warnings:        {len(result.warnings)}")
        lines.append("")

    errs, warns = len(result.errors), len(result.warnings)
    if errs:
        lines.append(f"knowledge base has errors ({errs} errors, {warns} warnings)")
    elif warns:
        lines.append(f"knowledge base has warnings ({warns} warnings)")
    else:
        lines.append("knowledge base is coherent (no issues found)")

    return "\n".join(lines)


def format_json(result: ValidationResult) -> str:
    return json.dumps(result.to_dict(), indent=2)


# CLI

def load_config(config_path: str, fs: FileSystem | None = None) -> KBConfig:
    fs = fs or RealFileSystem()
    data = json.loads(fs.read_text(config_path))
    entries = [
        KBEntry(name=e["name"], path=e["path"])
        for e in data.get("kb_roots", [])
    ]
    return KBConfig(entries=entries, namespace=data.get("namespace", ""))


def _get_git_changed_files() -> list[str]:
    """Get changed + untracked files from git (relative to repo root)."""
    import subprocess
    try:
        diff = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            capture_output=True, text=True, timeout=5,
        )
        files = diff.stdout.strip().split("\n") + untracked.stdout.strip().split("\n")
        return [f for f in files if f]
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return []


def _check_file_in_kb(config: KBConfig, file_path: str) -> bool:
    """Return True if *file_path* is inside any configured KB root."""
    from os.path import abspath, commonpath

    abs_file = abspath(file_path)
    for entry in config.entries:
        abs_root = abspath(entry.path)
        try:
            if commonpath([abs_file, abs_root]) == abs_root:
                return True
        except ValueError:
            continue
    return False


def _read_hook_input() -> dict | None:
    """Read hook JSON from stdin if available."""
    import select

    if not select.select([sys.stdin], [], [], 0)[0]:
        return None
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, AttributeError):
        return None


def main(argv: list[str] | None = None) -> int:
    import argparse

    default_cfg = ".claude/knowledge-base/config.json"

    parser = argparse.ArgumentParser(description="Validate knowledge base integrity")
    parser.add_argument("path", nargs="?", default=None, help="KB root directory (single KB, skips config)")
    parser.add_argument("--config", type=str, metavar="PATH", default=None, help=f"Config file path (default: {default_cfg})")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--hook", action="store_true", help="Hook mode: read stdin for context, errors to stderr with exit 2")
    args = parser.parse_args(argv)

    hook_input = _read_hook_input() if args.hook else None

    agent_root = ".claude/agents" if Path(".claude/agents").is_dir() else None

    if args.path:
        kb_root = args.path
        if not Path(kb_root).is_dir():
            print(f"ERROR: KB root '{kb_root}' does not exist.", file=sys.stderr)
            return 1
        result = validate_kb(kb_root, agent_root=agent_root)
        changed = _get_git_changed_files()
        if changed:
            result.issues.extend(check_changelog(changed, kb_root))
    else:
        cfg_path = args.config or default_cfg
        if not Path(cfg_path).exists():
            if args.config:
                print(f"ERROR: config file '{cfg_path}' not found.", file=sys.stderr)
                return 1
            kb_root = "."
            if not Path(kb_root).is_dir():
                print(f"ERROR: KB root '{kb_root}' does not exist.", file=sys.stderr)
                return 1
            result = validate_kb(kb_root, agent_root=agent_root)
            changed = _get_git_changed_files()
            if changed:
                result.issues.extend(check_changelog(changed, kb_root))
        else:
            config = load_config(cfg_path)

            if args.hook and hook_input:
                file_path = hook_input.get("tool_input", {}).get("file_path")
                if not file_path or not _check_file_in_kb(config, file_path):
                    return 0

            for entry in config.entries:
                if not Path(entry.path).is_dir():
                    print(f"ERROR: KB root '{entry.path}' (KB '{entry.name}') does not exist.", file=sys.stderr)
                    return 1

            result = validate_multi_kb(config, agent_root=agent_root)

    if args.hook:
        if result.errors or result.warnings:
            print(format_text(result, quiet=True), file=sys.stderr)
            return 2
        return 0
    elif args.json:
        print(format_json(result))
    else:
        print(format_text(result, quiet=args.quiet))

    return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
