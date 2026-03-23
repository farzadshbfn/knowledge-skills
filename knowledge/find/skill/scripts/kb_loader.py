#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""KB structure loader for /kb-find progressive loading."""

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol


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
                part.startswith(".") or part.startswith("__")
                for part in p.relative_to(root_path).parts
            )
        )


class MockFileSystem:
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


@dataclass
class KBEntry:
    name: str
    path: str
    readonly: bool = False


@dataclass
class KBConfig:
    entries: list[KBEntry]
    namespace: str = ""


@dataclass
class NoteMeta:
    path: str
    name: str = ""
    description: str = ""


@dataclass
class CategoryNode:
    path: str
    index: NoteMeta | None = None
    notes: list[NoteMeta] = field(default_factory=list)
    children: dict[str, "CategoryNode"] = field(default_factory=dict)
    skill: NoteMeta | None = None


@dataclass
class KBStructure:
    kb_root: str
    kb_name: str = ""
    readonly: bool = False
    tree: CategoryNode | None = None
    skills: list[NoteMeta] = field(default_factory=list)
    agents: list[NoteMeta] = field(default_factory=list)
    total_files: int = 0


@dataclass
class MultiKBStructure:
    kbs: list[KBStructure] = field(default_factory=list)


def extract_meta(content: str) -> tuple[str, str]:
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        return "", ""
    vals = {"name": "", "description": ""}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        for key in vals:
            m = re.match(rf"^{key}:\s*(.+)", line)
            if m:
                vals[key] = m.group(1).strip().strip('"').strip("'")
    return vals["name"], vals["description"]


def _navigate(root: CategoryNode, dir_parts: list[str], base_path: str) -> CategoryNode:
    node = root
    path_so_far = base_path
    for part in dir_parts:
        path_so_far = f"{path_so_far}/{part}" if path_so_far else part
        if part not in node.children:
            node.children[part] = CategoryNode(path=path_so_far)
        node = node.children[part]
    return node


_NON_TOPIC_FILES = {"CHANGELOG.md"}


def build_category_tree(
    files: dict[str, str],
) -> CategoryNode:
    root = CategoryNode(path="")

    for rel_path, content in sorted(files.items()):
        if Path(rel_path).name in _NON_TOPIC_FILES:
            continue

        parts = rel_path.split("/")
        fname, dir_parts = parts[-1], parts[:-1]
        name, desc = extract_meta(content)
        meta = NoteMeta(path=rel_path, name=name, description=desc)
        node = _navigate(root, dir_parts, "")

        if "/skill/" in rel_path:
            if fname == "SKILL.md":
                node.index = meta
                _navigate(root, dir_parts[:-1], "").skill = meta
            else:
                node.notes.append(meta)
        elif fname == "index.md" or fname.endswith("-index.md"):
            node.index = meta
        else:
            node.notes.append(meta)

    return root


def load_kb(
    kb_root: str,
    *,
    fs: FileSystem | None = None,
    agent_root: str | None = None,
) -> KBStructure:
    fs = fs or RealFileSystem()
    result = KBStructure(kb_root=kb_root)

    files: dict[str, str] = {}
    for rel_path in fs.list_md_files(kb_root):
        full = f"{kb_root}/{rel_path}"
        try:
            files[rel_path] = fs.read_text(full)
        except (OSError, UnicodeDecodeError):
            continue

    result.total_files = len(files)

    result.tree = build_category_tree(files)

    for rel_path, content in files.items():
        if rel_path.endswith("/skill/SKILL.md"):
            name, desc = extract_meta(content)
            result.skills.append(NoteMeta(path=rel_path, name=name, description=desc))


    if agent_root:
        result.agents = _load_agents(agent_root, fs)

    return result


def _load_agents(agent_root: str, fs: FileSystem) -> list[NoteMeta]:
    agents: list[NoteMeta] = []
    for rel in fs.list_md_files(agent_root):
        full = f"{agent_root}/{rel}"
        try:
            content = fs.read_text(full)
            name, desc = extract_meta(content)
            agents.append(NoteMeta(path=f".claude/agents/{rel}", name=name, description=desc))
        except (OSError, UnicodeDecodeError):
            continue
    return agents


def _prefix_note(note: NoteMeta, prefix: str) -> dict:
    return {"path": f"{prefix}{note.path}", "name": note.name, "description": note.description}


def node_to_dict(node: CategoryNode, path_prefix: str = "") -> dict:
    if path_prefix and node.path:
        full_path = f"{path_prefix}{node.path}"
    elif path_prefix:
        full_path = path_prefix.rstrip("/")
    else:
        full_path = node.path
    d: dict = {"path": full_path}
    if node.index:
        d["index"] = _prefix_note(node.index, path_prefix)
    if node.notes:
        d["notes"] = [_prefix_note(n, path_prefix) for n in node.notes]
    if node.skill:
        d["skill"] = _prefix_note(node.skill, path_prefix)
    if node.children:
        d["children"] = {k: node_to_dict(v, path_prefix) for k, v in sorted(node.children.items())}
    return d


def structure_to_dict(s: KBStructure) -> dict:
    prefix = f"{s.kb_root}/" if s.kb_root else ""
    d: dict = {
        "kb_root": s.kb_root,
        "kb_name": s.kb_name,
        "tree": node_to_dict(s.tree, prefix) if s.tree else None,
        "skills": [_prefix_note(sk, prefix) for sk in s.skills],
        "agents": [asdict(a) for a in s.agents],
        "total_files": s.total_files,
    }
    if s.readonly:
        d["readonly"] = True
    return d


def format_compact(multi: MultiKBStructure) -> str:
    lines: list[str] = []

    for kb in multi.kbs:
        lines.append(f"KB: {kb.kb_root} [{kb.kb_name}] ({kb.total_files} files)")

        def walk(node: CategoryNode, depth: int = 0) -> None:
            indent = "  " * depth
            if node.index:
                tag = f" [{node.skill.name}]" if node.skill else ""
                lines.append(f"{indent}{node.index.name}{tag}")
            for note in node.notes:
                lines.append(f"{indent}  - {note.name}: {note.description[:80]}")
            for child in node.children.values():
                walk(child, depth + 1)

        if kb.tree:
            walk(kb.tree)

    return "\n".join(lines)


_INFRA_FOLDERS = {"skill", "agents", "reference", "assets", "scripts", "legacy"}


def _skill_detail_lines(skill_node: CategoryNode, prefix: str) -> list[str]:
    """Render skill sub-folders as compact summary lines under the skill's parent."""
    lines: list[str] = []
    for folder_name in sorted(skill_node.children.keys()):
        child = skill_node.children[folder_name]
        stems = [Path(n.path).stem for n in child.notes]
        if child.index:
            stems.insert(0, Path(child.index.path).stem)
        summary = "{" + ", ".join(stems) + "}" if stems else ""
        lines.append(f"{prefix}╰ {folder_name}/ {summary}".rstrip())
    return lines


def _tree_lines(node: CategoryNode, prefix: str = "") -> list[str]:
    topic_children = {k: v for k, v in sorted(node.children.items()) if k not in _INFRA_FOLDERS}
    keys = list(topic_children.keys())
    lines: list[str] = []
    for i, key in enumerate(keys):
        child = topic_children[key]
        is_last = i == len(keys) - 1
        connector = "└─" if is_last else "├─"
        desc = f" — {child.index.description}" if child.index and child.index.description else ""
        skill_tag = " [skill]" if child.skill else ""
        lines.append(f"{prefix}{connector} {key}{skill_tag}{desc}")
        child_prefix = prefix + ("   " if is_last else "│  ")
        if child.skill and "skill" in child.children:
            lines.extend(_skill_detail_lines(child.children["skill"], child_prefix))
        lines.extend(_tree_lines(child, child_prefix))
    return lines


def format_list_topics(multi: MultiKBStructure) -> str:
    sections: list[str] = []
    for kb in multi.kbs:
        if not kb.tree or not kb.tree.children:
            continue
        badge = " [read-only]" if kb.readonly else ""
        lines = [f"@{kb.kb_name}{badge}"]
        lines.extend(_tree_lines(kb.tree))
        sections.append("\n".join(lines))
    return "\n\n".join(sections) if sections else "Topics (0 categories):"


def _resolve_path(tree: CategoryNode, path: str) -> CategoryNode | None:
    node = tree
    for part in path.split("/"):
        if part not in node.children:
            return None
        node = node.children[part]
    return node


def filter_topic(multi: MultiKBStructure, topic: str) -> tuple[str, dict] | None:
    # @kb-name/path syntax — restrict to a specific KB
    if topic.startswith("@"):
        rest = topic[1:]
        if "/" not in rest:
            return None
        kb_name, path = rest.split("/", 1)
        for kb in multi.kbs:
            if kb.kb_name != kb_name:
                continue
            if kb.tree:
                node = _resolve_path(kb.tree, path)
                if node:
                    prefix = f"{kb.kb_root}/" if kb.kb_root else ""
                    return kb.kb_name, node_to_dict(node, path_prefix=prefix)
        return None

    # Regular lookup — supports slash paths (parent/child)
    for kb in multi.kbs:
        if kb.tree:
            node = _resolve_path(kb.tree, topic)
            if node:
                prefix = f"{kb.kb_root}/" if kb.kb_root else ""
                return kb.kb_name, node_to_dict(node, path_prefix=prefix)
    return None


def load_multi_kb(
    config: KBConfig,
    *,
    fs: FileSystem | None = None,
) -> MultiKBStructure:
    fs = fs or RealFileSystem()
    result = MultiKBStructure()
    for entry in config.entries:
        kb = load_kb(entry.path, fs=fs)
        kb.kb_name = entry.name
        kb.readonly = entry.readonly
        result.kbs.append(kb)
    return result


def load_config(config_path: str, fs: FileSystem | None = None) -> KBConfig:
    fs = fs or RealFileSystem()
    data = json.loads(fs.read_text(config_path))
    entries = [
        KBEntry(name=e["name"], path=e["path"])
        for e in data.get("kb_roots", [])
    ]
    return KBConfig(entries=entries, namespace=data.get("namespace", ""))


def resolve_home_path(path: str) -> str:
    if path.startswith("~/"):
        return str(Path.home() / path[2:])
    return path


_GLOBAL_CONFIG = "~/.claude/knowledge-base/config.json"


def load_global_config(
    config_path: str = _GLOBAL_CONFIG,
    fs: FileSystem | None = None,
) -> KBConfig | None:
    fs = fs or RealFileSystem()
    resolved = resolve_home_path(config_path)
    if not fs.exists(resolved):
        return None
    data = json.loads(fs.read_text(resolved))
    namespace = data.get("namespace", "")
    source = data.get("source", "")
    if not source:
        return None
    source = resolve_home_path(source)
    # Read the source project's own config
    source_config_path = f"{source}/.claude/knowledge-base/config.json"
    if not fs.exists(source_config_path):
        return None
    source_data = json.loads(fs.read_text(source_config_path))
    entries = []
    for e in source_data.get("kb_roots", []):
        name = f"{namespace}.{e['name']}" if namespace else e["name"]
        # Resolve source KB paths relative to the source project root
        kb_path = e["path"]
        if kb_path.startswith("./"):
            kb_path = f"{source}/{kb_path[2:]}"
        elif not kb_path.startswith("/"):
            kb_path = f"{source}/{kb_path}"
        entries.append(KBEntry(name=name, path=kb_path, readonly=True))
    return KBConfig(entries=entries, namespace=namespace)


def merge_configs(
    project: KBConfig,
    global_: KBConfig | None,
) -> KBConfig:
    if global_ is None:
        return project
    merged = list(project.entries)
    project_names = {e.name for e in project.entries}
    project_paths = {str(Path(e.path).resolve()) for e in project.entries}
    for entry in global_.entries:
        # Skip if name collides or resolved path already in project
        if entry.name in project_names:
            continue
        if str(Path(entry.path).resolve()) in project_paths:
            continue
        merged.append(entry)
    return KBConfig(entries=merged, namespace=project.namespace)


def _err(msg: str) -> int:
    print(f"ERROR: {msg}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--config", type=str, metavar="PATH")
    parser.add_argument("--no-global", action="store_true",
                        help="Skip loading global KB config")
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument("--compact", action="store_true")
    output_group.add_argument("--list-topics", action="store_true")
    output_group.add_argument("--topic", type=str, metavar="NAME")
    args = parser.parse_args(argv)

    agent_root = ".claude/agents" if Path(".claude/agents").is_dir() else None

    # Load global config (unless opted out)
    global_config = None if args.no_global else load_global_config()

    # Auto-detect config: explicit --config, or default path if it exists
    cfg = args.config or ".claude/knowledge-base/config.json"
    if Path(cfg).exists():
        config = load_config(cfg)
        config = merge_configs(config, global_config)
        for entry in config.entries:
            if not Path(entry.path).is_dir():
                if entry.readonly:
                    continue  # skip missing global KBs silently
                return _err(f"KB root '{entry.path}' not found")
        # Filter out missing readonly entries before loading
        config = KBConfig(
            entries=[e for e in config.entries if Path(e.path).is_dir()],
            namespace=config.namespace,
        )
        multi = load_multi_kb(config)
    else:
        if args.config:
            return _err(f"Config not found: {cfg}")
        kb_root = args.path
        if not Path(kb_root).is_dir():
            return _err(f"KB root '{kb_root}' not found")
        structure = load_kb(kb_root, agent_root=agent_root)
        structure.kb_name = "default"
        # Still merge global KBs even without project config
        if global_config:
            project_config = KBConfig(entries=[KBEntry("default", kb_root)])
            merged = merge_configs(project_config, global_config)
            # Filter out missing readonly entries
            merged = KBConfig(
                entries=[e for e in merged.entries
                         if Path(e.path).is_dir() or not e.readonly],
                namespace=merged.namespace,
            )
            multi = load_multi_kb(merged)
            multi.kbs[0] = structure  # keep original (has agents)
        else:
            multi = MultiKBStructure(kbs=[structure])

    agents = _load_agents(agent_root, RealFileSystem()) if agent_root else []

    if args.list_topics:
        print(format_list_topics(multi))
    elif args.topic:
        result = filter_topic(multi, args.topic)
        if result is None:
            return _err(f"topic '{args.topic}' not found")
        _, subtree = result
        print(json.dumps(subtree, indent=2))
    elif args.compact:
        print(format_compact(multi))
    else:
        print(json.dumps({"kbs": [structure_to_dict(kb) for kb in multi.kbs], "agents": [asdict(a) for a in agents]}, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
