#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""KB Viewer — Local HTTP server for browsing knowledge bases.

Reads .claude/knowledge-base/config.json, serves a single-page HTML viewer
that renders all configured KBs with working links and AI-powered search.
"""

import http.server
import json
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any

DEFAULT_PORT = 8787

_SKIP_PREFIXES = (".", "__")


def _should_skip(path: Path, root: Path) -> bool:
    """Return True if any path component starts with a dot or double underscore."""
    return any(
        part.startswith(_SKIP_PREFIXES)
        for part in path.relative_to(root).parts
    )


# ---------------------------------------------------------------------------
# Pure helpers (testable without HTTP)
# ---------------------------------------------------------------------------

def load_config(project_root: str) -> dict:
    """Load KB config from .claude/knowledge-base/config.json."""
    config_path = Path(project_root) / ".claude" / "knowledge-base" / "config.json"
    if not config_path.exists():
        return {"kb_roots": []}
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def resolve_kb_path(config: dict, kb_name: str) -> str | None:
    """Get filesystem path for a named KB."""
    for entry in config.get("kb_roots", []):
        if entry["name"] == kb_name:
            return entry["path"].rstrip("/")
    return None


def strip_frontmatter(content: str) -> tuple[dict, str]:
    """Strip YAML frontmatter, return (meta_dict, body)."""
    if not content.startswith("---"):
        return {}, content

    lines = content.split("\n")
    end = -1
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break

    if end == -1:
        return {}, content

    meta: dict[str, str] = {}
    for line in lines[1:end]:
        m = re.match(r"^(\w[\w-]*):\s*(.+)", line)
        if m:
            meta[m.group(1)] = m.group(2).strip().strip('"').strip("'")

    body = "\n".join(lines[end + 1:])
    return meta, body


def resolve_cross_kb_links(content: str, config: dict) -> str:
    """Replace @kb-name/path markdown links with viewer-navigable paths."""
    def replace_link(m: re.Match) -> str:
        text = m.group(1)
        kb_name = m.group(2)
        path = m.group(3)
        kb_path = resolve_kb_path(config, kb_name)
        if kb_path:
            resolved = f"{kb_path}/{path}"
            return f"[{text}]({resolved})"
        return m.group(0)

    return re.sub(r"\[([^\]]+)\]\(@([^/]+)/([^)]+)\)", replace_link, content)


def fuzzy_match(query: str, candidate: str) -> int | None:
    """Subsequence match with gap scoring. Returns total gap or None.

    Finds the shortest window in *candidate* that contains *query* as a
    subsequence. The score is ``window_length - len(query)`` (i.e. total
    inserted chars). Lower = better.

    Returns None when *query* is not a subsequence of *candidate*.
    """
    q = query.lower()
    c = candidate.lower()

    if not q:
        return 0
    if len(q) > len(c):
        return None

    best: int | None = None
    qi = 0
    ci = 0

    while ci < len(c):
        if c[ci] == q[qi]:
            qi += 1
            if qi == len(q):
                # Complete forward match ending at ci — tighten backward.
                end = ci
                qi = len(q) - 1
                while qi >= 0:
                    if c[ci] == q[qi]:
                        qi -= 1
                    ci -= 1
                ci += 1  # ci is now the window start

                gap = (end - ci + 1) - len(q)
                if best is None or gap < best:
                    best = gap

                # Resume search from next char after window start.
                qi = 0
                ci += 1
                continue
        ci += 1

    return best


def is_safe_path(project_root: str, rel_path: str) -> bool:
    """Check that a relative path doesn't escape the project root."""
    full = (Path(project_root) / rel_path).resolve()
    root = Path(project_root).resolve()
    return str(full).startswith(str(root))


def build_graph(project_root: str, config: dict) -> dict:
    """Build a graph of all KB files and their inter-file links.

    Returns {"nodes": [...], "edges": [...]} where each node has
    id, name, kb, folder, ref_count and each edge has source, target.
    """
    project = Path(project_root).resolve()
    nodes: dict[str, dict] = {}
    raw_edges: list[tuple[str, str, Path]] = []  # (source_id, link_path, source_file)

    for entry in config.get("kb_roots", []):
        kb_name = entry["name"]
        kb_rel = entry["path"].rstrip("/")  # normalize e.g. "./knowledge/" → "./knowledge"
        kb_path = (project / kb_rel).resolve()
        topics = kb_path 
        if not topics.is_dir():
            continue

        for md_file in topics.rglob("*.md"):
            if _should_skip(md_file, kb_path):
                continue
            rel_to_kb = str(md_file.relative_to(kb_path))
            node_id = kb_rel + "/" + rel_to_kb
            try:
                content = md_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            meta, body = strip_frontmatter(content)
            body = resolve_cross_kb_links(body, config)

            folder = str(md_file.parent.relative_to(kb_path))
            nodes[node_id] = {
                "id": node_id,
                "name": meta.get("name", md_file.stem),
                "kb": kb_name,
                "folder": folder,
                "ref_count": 0,
            }

            # Extract markdown links: [text](target)
            for link_target in re.findall(r"\]\(([^)]+)\)", body):
                if link_target.startswith(("http://", "https://", "#")):
                    continue
                link_path = link_target.split("#")[0]
                if not link_path or not link_path.endswith(".md"):
                    continue
                raw_edges.append((node_id, link_path, md_file))

    # Resolve raw edges to node IDs
    edges: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for source_id, link_path, source_file in raw_edges:
        if link_path.startswith("./") or link_path.startswith("/"):
            resolved = (project / link_path).resolve()
        else:
            resolved = (source_file.parent / link_path).resolve()
        try:
            resolved_rel = resolved.relative_to(project)
        except ValueError:
            continue

        # Map filesystem path back to a node ID
        target_id = None
        rel_str = str(resolved_rel)
        for e in config.get("kb_roots", []):
            kb_prefix = e["path"].rstrip("/")
            norm = kb_prefix.removeprefix("./")
            if rel_str.startswith(norm + "/"):
                target_id = kb_prefix + rel_str[len(norm):]
                break

        if (
            target_id
            and target_id in nodes
            and target_id != source_id
            and (source_id, target_id) not in seen
        ):
            seen.add((source_id, target_id))
            edges.append({"source": source_id, "target": target_id})

    for edge in edges:
        nodes[edge["target"]]["ref_count"] += 1

    return {"nodes": list(nodes.values()), "edges": edges}


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class KBViewerHandler(http.server.BaseHTTPRequestHandler):
    """Serves the KB viewer SPA and API endpoints."""

    project_root: str = ""
    viewer_dir: str = ""
    kb_config: dict = {}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._serve_html()
        elif path == "/graph.js":
            self._serve_static("graph.js", "application/javascript")
        elif path == "/api/tree":
            self._serve_tree()
        elif path == "/api/file":
            file_path = params.get("path", [None])[0]
            if file_path:
                self._serve_file(file_path)
            else:
                self._error(400, "Missing 'path' parameter")
        elif path == "/api/config":
            self._serve_config()
        elif path == "/api/graph":
            self._serve_graph()
        elif path == "/api/search":
            query = params.get("q", [None])[0]
            if query:
                self._serve_search(query)
            else:
                self._error(400, "Missing 'q' parameter")
        else:
            # SPA fallback: serve index.html for any path (client-side routing)
            self._serve_html()

    def _serve_html(self):
        html_path = Path(self.viewer_dir) / "index.html"
        content = html_path.read_text(encoding="utf-8")
        self._respond(200, content, "text/html")

    def _serve_static(self, filename: str, content_type: str):
        file_path = Path(self.viewer_dir) / filename
        if not file_path.exists():
            self._error(404, f"{filename} not found")
            return
        content = file_path.read_text(encoding="utf-8")
        self._respond(200, content, content_type)

    def _serve_tree(self):
        """Call kb_loader.py to get KB tree structure."""
        loader = self._find_kb_loader()
        if not loader:
            self._error(500, "kb_loader.py not found in any configured KB")
            return

        try:
            result = subprocess.run(
                ["uv", "run", str(loader)],
                capture_output=True, text=True, timeout=10,
                cwd=self.project_root,
            )
            if result.returncode == 0:
                self._respond(200, result.stdout, "application/json")
            else:
                self._error(500, f"kb_loader error: {result.stderr}")
        except subprocess.TimeoutExpired:
            self._error(504, "kb_loader timed out")
        except FileNotFoundError:
            self._error(500, "uv not found")

    def _serve_file(self, rel_path: str):
        """Serve a markdown file with parsed frontmatter."""
        if not is_safe_path(self.project_root, rel_path):
            self._error(403, "Path traversal not allowed")
            return

        full_path = Path(self.project_root) / rel_path
        if not full_path.exists():
            self._error(404, f"File not found: {rel_path}")
            return

        content = full_path.read_text(encoding="utf-8")
        meta, body = strip_frontmatter(content)
        body = resolve_cross_kb_links(body, self.kb_config)

        response = json.dumps({"path": rel_path, "meta": meta, "body": body})
        self._respond(200, response, "application/json")

    def _serve_config(self):
        self._respond(200, json.dumps(self.kb_config), "application/json")

    def _serve_graph(self):
        """Return the file link graph for mind-map visualization."""
        graph = build_graph(self.project_root, self.kb_config)
        self._respond(200, json.dumps(graph), "application/json")

    def _serve_search(self, query: str):
        """Fuzzy search across all KB notes (name + description)."""
        hits: list[dict] = []
        for entry in self.kb_config.get("kb_roots", []):
            kb_path = Path(self.project_root) / entry["path"]
            topics = kb_path 
            if not topics.is_dir():
                continue
            for md in topics.rglob("*.md"):
                if _should_skip(md, kb_path):
                    continue
                # Skip skill internals
                rel = str(md.relative_to(Path(self.project_root)))
                if "/skill/" in rel and not rel.endswith("/skill/SKILL.md"):
                    continue
                try:
                    content = md.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                meta, _ = strip_frontmatter(content)
                name = meta.get("name", md.stem)
                desc = meta.get("description", "")
                # Name match prioritized over description
                s_name = fuzzy_match(query, name)
                s_desc = fuzzy_match(query, desc)
                if s_name is None and s_desc is None:
                    continue
                # Name matches sort before description-only matches
                if s_name is not None:
                    sort_key = s_name
                else:
                    sort_key = 10000 + (s_desc or 0)
                hits.append({
                    "path": rel,
                    "name": name,
                    "description": desc[:200],
                    "score": sort_key,
                    "kb": entry["name"],
                })
        hits.sort(key=lambda h: h["score"])
        self._respond(200, json.dumps({"query": query, "results": hits[:30]}),
                       "application/json")

    def _find_kb_loader(self) -> Path | None:
        """Locate kb_loader.py in the configured KBs or project root."""
        # Search inside each configured KB
        for entry in self.kb_config.get("kb_roots", []):
            kb_path = Path(self.project_root) / entry["path"]
            for candidate in kb_path.rglob("kb_loader.py"):
                if "skill/scripts" in str(candidate):
                    return candidate
        # Fallback: search the entire project root (handles plugin installs
        # where kb_loader lives outside the user's KB paths)
        for candidate in Path(self.project_root).rglob("kb_loader.py"):
            if "skill/scripts" in str(candidate):
                return candidate
        return None

    def _respond(self, code: int, body: str, content_type: str):
        self.send_response(code)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _error(self, code: int, message: str):
        self._respond(code, json.dumps({"error": message}), "application/json")

    def log_message(self, format, *args):
        if os.environ.get("KB_VIEWER_VERBOSE"):
            super().log_message(format, *args)


# ---------------------------------------------------------------------------
# Server factory (for testing)
# ---------------------------------------------------------------------------

def create_server(
    port: int,
    project_root: str,
    viewer_dir: str,
) -> http.server.HTTPServer:
    """Create and return a ThreadingHTTPServer (does not start it).

    Threading prevents slow requests (e.g. kb_loader subprocess) from
    blocking concurrent browser requests for static assets.
    """
    config = load_config(project_root)

    KBViewerHandler.project_root = project_root
    KBViewerHandler.viewer_dir = viewer_dir
    KBViewerHandler.kb_config = config

    http.server.ThreadingHTTPServer.allow_reuse_address = True
    return http.server.ThreadingHTTPServer(("127.0.0.1", port), KBViewerHandler)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="KB Viewer — browse knowledge bases locally"
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT,
        help=f"Port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--project-root", type=str, default=None,
        help="Project root (default: auto-detect)",
    )
    args = parser.parse_args(argv)

    if args.project_root:
        project_root = str(Path(args.project_root).resolve())
    else:
        candidate = Path(__file__).resolve().parent
        while candidate != candidate.parent:
            if (candidate / ".claude" / "knowledge-base" / "config.json").exists():
                project_root = str(candidate)
                break
            candidate = candidate.parent
        else:
            print(
                "ERROR: Could not find project root "
                "(.claude/knowledge-base/config.json)",
                file=sys.stderr,
            )
            return 1

    viewer_dir = str(Path(__file__).resolve().parent)
    server = create_server(args.port, project_root, viewer_dir)

    config = load_config(project_root)
    kb_names = ", ".join(e["name"] for e in config.get("kb_roots", []))

    print(f"KB Viewer running at http://127.0.0.1:{args.port}")
    print(f"Project root: {project_root}")
    print(f"KBs: {kb_names or '(none)'}")
    print("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
