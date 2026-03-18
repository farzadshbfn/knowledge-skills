#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pytest"]
# ///
"""Tests for KB Viewer graph endpoint and build_graph."""

import json
import threading
import urllib.request
from pathlib import Path

import pytest

from serve import build_graph, create_server, load_config

# ---------------------------------------------------------------------------
# Fixture: project with inter-file links
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def graph_project(tmp_path_factory):
    """Project with inter-file links for graph testing."""
    tmp_path = tmp_path_factory.mktemp("graph")
    config_dir = tmp_path / ".claude" / "knowledge-base"
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text(json.dumps({
        "kb_roots": [
            {"name": "core", "path": "./knowledge"},
            {"name": "extra", "path": "./extra"},
        ]
    }))
    core = tmp_path / "knowledge" 
    (core / "tools").mkdir(parents=True)
    (core / "index.md").write_text(
        "---\nname: Root\ndescription: Root index\n---\n\n"
        "- [Tools](tools/index.md)\n"
    )
    (core / "tools" / "index.md").write_text(
        "---\nname: Tools\ndescription: Tooling\n---\n\n"
        "## Topics\n\n- [CLI](#cli)\n\n## CLI\n\nCommand line."
    )
    (core / "tools" / "editors.md").write_text(
        "---\nname: Editors\ndescription: Code editors\n---\n\n"
        "See [tools index](index.md) and [root](../index.md)."
    )
    # Orphan note — no links to or from it
    (core / "tools" / "orphan.md").write_text(
        "---\nname: Orphan\ndescription: Lonely note\n---\n\nNo links here."
    )
    extra = tmp_path / "extra" 
    (extra / "misc").mkdir(parents=True)
    (extra / "misc" / "index.md").write_text(
        "---\nname: Misc\ndescription: Miscellaneous\n---\n\n"
        "Cross-KB: [Tools](@core/tools/index.md)\n"
    )
    return tmp_path

# ---------------------------------------------------------------------------
# Unit tests: build_graph
# ---------------------------------------------------------------------------

class TestBuildGraph:
    def test_returns_nodes_and_edges(self, graph_project):
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        assert "nodes" in g
        assert "edges" in g
        assert len(g["nodes"]) > 0

    def test_node_fields(self, graph_project):
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        for node in g["nodes"]:
            assert "id" in node
            assert "name" in node
            assert "kb" in node
            assert "folder" in node
            assert "ref_count" in node
            assert isinstance(node["ref_count"], int)

    def test_edges_reference_valid_nodes(self, graph_project):
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        ids = {n["id"] for n in g["nodes"]}
        for edge in g["edges"]:
            assert edge["source"] in ids, f"source {edge['source']} not in nodes"
            assert edge["target"] in ids, f"target {edge['target']} not in nodes"

    def test_ref_count_matches_incoming_edges(self, graph_project):
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        incoming = {}
        for edge in g["edges"]:
            incoming[edge["target"]] = incoming.get(edge["target"], 0) + 1
        for node in g["nodes"]:
            assert node["ref_count"] == incoming.get(node["id"], 0), (
                f"Node {node['id']}: ref_count={node['ref_count']} "
                f"but incoming edges={incoming.get(node['id'], 0)}"
            )

    def test_both_kbs_represented(self, graph_project):
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        kbs = {n["kb"] for n in g["nodes"]}
        assert "core" in kbs
        assert "extra" in kbs

    def test_cross_kb_edge_exists(self, graph_project):
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        node_kb = {n["id"]: n["kb"] for n in g["nodes"]}
        cross = [e for e in g["edges"]
                 if node_kb.get(e["source"]) != node_kb.get(e["target"])]
        assert len(cross) > 0, "Expected at least one cross-KB edge"

    def test_anchor_only_links_excluded(self, graph_project):
        """Links like (#section) should not produce edges."""
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        for edge in g["edges"]:
            assert "#" not in edge["source"]
            assert "#" not in edge["target"]

    def test_no_self_edges(self, graph_project):
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        for edge in g["edges"]:
            assert edge["source"] != edge["target"]

    def test_no_duplicate_edges(self, graph_project):
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        seen = set()
        for edge in g["edges"]:
            key = (edge["source"], edge["target"])
            assert key not in seen, f"Duplicate edge: {key}"
            seen.add(key)

    def test_tools_index_has_highest_ref_count(self, graph_project):
        """Tools index is linked from editors.md, root index, and cross-KB misc."""
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        by_name = {n["name"]: n for n in g["nodes"]}
        tools = by_name["Tools"]
        assert tools["ref_count"] == 3

    def test_connection_count_includes_outgoing(self, graph_project):
        """Client sizes nodes by total connections (in + out), not just ref_count."""
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        conn = {}
        for e in g["edges"]:
            conn[e["source"]] = conn.get(e["source"], 0) + 1
            conn[e["target"]] = conn.get(e["target"], 0) + 1
        by_name = {n["name"]: n for n in g["nodes"]}
        assert conn[by_name["Editors"]["id"]] == 2
        assert conn[by_name["Root"]["id"]] == 2
        assert conn[by_name["Tools"]["id"]] == 3

    def test_node_ids_loadable_via_file_api(self, graph_project, graph_server):
        """Graph node IDs should be valid paths for the file API."""
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        for node in g["nodes"]:
            url = f"{graph_server}/api/file?path={node['id']}"
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read().decode())
            assert data["meta"].get("name"), f"Node {node['id']} not loadable"

    def test_orphan_nodes_exist(self, graph_project):
        """Graph includes nodes with zero connections (orphans)."""
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        conn = set()
        for e in g["edges"]:
            conn.add(e["source"])
            conn.add(e["target"])
        orphans = [n for n in g["nodes"] if n["id"] not in conn]
        assert len(orphans) > 0, "Expected at least one orphan node"
        orphan_names = {n["name"] for n in orphans}
        assert "Orphan" in orphan_names

    def test_incoming_vs_outgoing_counts(self, graph_project):
        """Verify separate in/out counts for size mode switching."""
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        in_count, out_count = {}, {}
        for e in g["edges"]:
            out_count[e["source"]] = out_count.get(e["source"], 0) + 1
            in_count[e["target"]] = in_count.get(e["target"], 0) + 1
        by_name = {n["name"]: n for n in g["nodes"]}
        # Editors has 2 outgoing, 0 incoming
        assert out_count.get(by_name["Editors"]["id"], 0) == 2
        assert in_count.get(by_name["Editors"]["id"], 0) == 0
        # Tools has 0 outgoing, 3 incoming
        assert out_count.get(by_name["Tools"]["id"], 0) == 0
        assert in_count.get(by_name["Tools"]["id"], 0) == 3

    def test_all_files_included(self, graph_project):
        """Graph includes all .md files, not just non-skill files."""
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        names = {n["name"] for n in g["nodes"]}
        # All 5 files from fixture should be present (including orphan)
        assert "Root" in names
        assert "Tools" in names
        assert "Editors" in names
        assert "Misc" in names
        assert "Orphan" in names

    def test_trailing_slash_in_config_path(self, tmp_path):
        """Trailing slash in kb_roots path must not break node IDs or edges."""
        # Use isolated tmp_path to avoid mutating session-scoped graph_project config
        config_dir = tmp_path / ".claude" / "knowledge-base"
        config_dir.mkdir(parents=True)
        (config_dir / "config.json").write_text(json.dumps({
            "kb_roots": [
                {"name": "core", "path": "./knowledge/"},
                {"name": "extra", "path": "./extra/"},
            ]
        }))
        core = tmp_path / "knowledge" / "tools"
        core.mkdir(parents=True)
        (tmp_path / "knowledge" / "index.md").write_text(
            "---\nname: Root\ndescription: Root\n---\n\n- [Tools](tools/index.md)\n"
        )
        (core / "index.md").write_text(
            "---\nname: Tools\ndescription: Tooling\n---\n\nContent."
        )
        (core / "editors.md").write_text(
            "---\nname: Editors\ndescription: Editors\n---\n\nSee [index](index.md) and [root](../index.md)."
        )
        extra = tmp_path / "extra" / "misc"
        extra.mkdir(parents=True)
        (extra / "index.md").write_text(
            "---\nname: Misc\ndescription: Misc\n---\n\nCross-KB: [Tools](@core/tools/index.md)\n"
        )
        config = load_config(str(tmp_path))
        g = build_graph(str(tmp_path), config)
        # Node IDs must not contain double slashes
        for node in g["nodes"]:
            assert "//" not in node["id"], f"Double slash in node ID: {node['id']}"
        # Edges must still resolve (editors.md links to index.md and ../index.md)
        assert len(g["edges"]) > 0, "Trailing slash broke edge resolution"
        # All edges must reference valid nodes
        ids = {n["id"] for n in g["nodes"]}
        for edge in g["edges"]:
            assert edge["source"] in ids, f"source {edge['source']} not in nodes"
            assert edge["target"] in ids, f"target {edge['target']} not in nodes"

# ---------------------------------------------------------------------------
# Integration: graph endpoint via HTTP
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def graph_server(graph_project):
    viewer_dir = str(Path(__file__).resolve().parent.parent.parent / "knowledge" / "view" / "skill" / "scripts")
    server = create_server(0, str(graph_project), viewer_dir)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()

class TestGraphHTTP:
    def _get(self, url):
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())

    def _get_html(self, url):
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, resp.read().decode()

    def test_graph_endpoint(self, graph_server):
        status, data = self._get(f"{graph_server}/api/graph")
        assert status == 200
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) >= 3

    def test_graph_js_served(self, graph_server):
        status, body = self._get_html(f"{graph_server}/graph.js")
        assert status == 200
        assert "renderGraph" in body

    def test_view_graph_url(self, graph_server):
        status, html = self._get_html(f"{graph_server}/?view=graph")
        assert status == 200
        assert "KB Viewer" in html

    def test_html_includes_d3_and_graph(self, graph_server):
        status, html = self._get_html(f"{graph_server}/")
        assert status == 200
        assert "d3" in html.lower()
        assert "graph.js" in html

    def test_html_has_theme_support(self, graph_server):
        """HTML includes theme CSS variables and toggle."""
        status, html = self._get_html(f"{graph_server}/")
        assert status == 200
        assert 'data-theme="dark"' in html
        assert "cycleTheme" in html
        assert "theme-toggle" in html
        # Both light and dark themes define key variables
        assert "--edge:" in html
        assert "--link:" in html

    def test_graph_js_uses_css_vars(self, graph_server):
        """graph.js reads colors from CSS variables, not hardcoded."""
        _, js = self._get_html(f"{graph_server}/graph.js")
        assert "cssVar" in js
        assert "--edge" in js
        # Should NOT have hardcoded hex colors for edges
        assert '"#7c8aaa"' not in js
        assert '"#4a5568"' not in js

    def test_graph_js_has_kb_sep_control(self, graph_server):
        """graph.js has KB cluster spread slider."""
        _, js = self._get_html(f"{graph_server}/graph.js")
        assert "gc-cluster" in js
        assert "centralForce" in js

    def test_graph_js_has_glow_filters(self, graph_server):
        """graph.js creates SVG glow filters for hover radiance."""
        _, js = self._get_html(f"{graph_server}/graph.js")
        assert "glow-strong" in js
        assert "glow-soft" in js
        assert "feGaussianBlur" in js

    def test_graph_js_has_controls_panel(self, graph_server):
        """graph.js builds a controls panel with expected config options."""
        _, js = self._get_html(f"{graph_server}/graph.js")
        assert "gc-repel" in js
        assert "gc-dist" in js
        assert "gc-cluster" in js
        assert "gc-fade" in js
        assert "gc-size" in js
        assert "gc-orphans" in js

    def test_graph_js_boundary_slider_can_access_hulls(self, graph_server):
        """Boundary slider handler references hull vars that must be in scope."""
        _, js = self._get_html(f"{graph_server}/graph.js")
        assert "gc-boundary" in js
        # hullEntries must be declared at module scope (let/var), not const inside renderGraph,
        # so buildControlsPanel can access them
        assert "let hullEntries" in js or "var hullEntries" in js

    def test_graph_js_has_focus_function(self, graph_server):
        """graph.js exposes focusGraphNode for sidebar integration."""
        _, js = self._get_html(f"{graph_server}/graph.js")
        assert "function focusGraphNode" in js

    def test_graph_js_auto_focuses_current_note(self, graph_server):
        """setView('graph') focuses the currently viewed note on the graph."""
        _, js = self._get_html(f"{graph_server}/graph.js")
        # setView should read currentPath and pass it to focusGraphNode
        assert "currentPath" in js
        assert "focusGraphNode(focusPath)" in js

    def test_graph_js_served_at_absolute_path(self, graph_server):
        """graph.js must be referenced with absolute path /graph.js in HTML."""
        _, html = self._get_html(f"{graph_server}/")
        assert 'src="/graph.js"' in html

    def test_graph_js_loads_from_deep_url(self, graph_server):
        """graph.js must load correctly even when SPA serves a deep path."""
        # SPA fallback serves index.html for any path — graph.js must still resolve
        _, html = self._get_html(f"{graph_server}/core/topic/note.md")
        assert 'src="/graph.js"' in html
        # Verify /graph.js itself is reachable
        _, js = self._get_html(f"{graph_server}/graph.js")
        assert "function setView" in js

    def test_graph_js_config_defaults(self, graph_server):
        """graph.js has expected config defaults."""
        _, js = self._get_html(f"{graph_server}/graph.js")
        assert "fadeCoef:" in js
        assert "showOrphans:" in js
        assert 'sizeMode: "both"' in js

    def test_dark_theme_variables(self, graph_server):
        """Dark theme defines inverted colors for key variables."""
        _, html = self._get_html(f"{graph_server}/")
        # Dark theme text should be light
        assert "--text: #cdd6f4" in html
        # Dark theme card-bg should be dark
        assert "--card-bg: #1e1e2e" in html

    def test_search_input_uses_theme_vars(self, graph_server):
        """Search input uses CSS variables for background/color."""
        _, html = self._get_html(f"{graph_server}/")
        assert "background: var(--card-bg)" in html
        # text color on input
        assert "color: var(--text)" in html

    def test_theme_persists_via_localstorage(self, graph_server):
        """Theme toggle code uses localStorage for persistence."""
        _, html = self._get_html(f"{graph_server}/")
        assert "localStorage" in html
        assert "kb-theme" in html

    def test_sidebar_has_kb_root_click(self, graph_server):
        """Sidebar KB labels load root index on click."""
        _, html = self._get_html(f"{graph_server}/")
        assert "kb.tree.index" in html or "kb.tree && kb.tree.index" in html

# ---------------------------------------------------------------------------
# Unit tests: orphan identification
# ---------------------------------------------------------------------------

class TestOrphanNodes:
    def test_orphan_has_zero_ref_count(self, graph_project):
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        orphan = next(n for n in g["nodes"] if n["name"] == "Orphan")
        assert orphan["ref_count"] == 0

    def test_orphan_has_no_edges(self, graph_project):
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        orphan = next(n for n in g["nodes"] if n["name"] == "Orphan")
        edge_ids = set()
        for e in g["edges"]:
            edge_ids.add(e["source"])
            edge_ids.add(e["target"])
        assert orphan["id"] not in edge_ids

    def test_connected_nodes_have_edges(self, graph_project):
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        edge_ids = set()
        for e in g["edges"]:
            edge_ids.add(e["source"])
            edge_ids.add(e["target"])
        connected = [n for n in g["nodes"] if n["name"] != "Orphan"]
        for n in connected:
            assert n["id"] in edge_ids, f"{n['name']} should have edges"

# ---------------------------------------------------------------------------
# Unit tests: cross-KB edge identification
# ---------------------------------------------------------------------------

class TestCrossKBEdges:
    def test_cross_kb_edges_identifiable(self, graph_project):
        """Edges between different KBs can be distinguished from intra-KB edges."""
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        node_kb = {n["id"]: n["kb"] for n in g["nodes"]}
        cross = [e for e in g["edges"]
                 if node_kb[e["source"]] != node_kb[e["target"]]]
        intra = [e for e in g["edges"]
                 if node_kb[e["source"]] == node_kb[e["target"]]]
        assert len(cross) > 0, "Expected cross-KB edges"
        assert len(intra) > 0, "Expected intra-KB edges"

    def test_cross_kb_edge_connects_different_kbs(self, graph_project):
        """Each cross-KB edge has source and target in different KBs."""
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        node_kb = {n["id"]: n["kb"] for n in g["nodes"]}
        for e in g["edges"]:
            src_kb = node_kb[e["source"]]
            tgt_kb = node_kb[e["target"]]
            if src_kb != tgt_kb:
                assert src_kb in ("core", "extra")
                assert tgt_kb in ("core", "extra")

    def test_graph_nodes_have_kb_field(self, graph_project):
        """Every node has a kb field for client-side KB grouping."""
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        for node in g["nodes"]:
            assert node["kb"] in ("core", "extra"), f"Unexpected kb: {node['kb']}"

    def test_graph_js_distinguishes_cross_kb_edges(self, graph_server):
        """graph.js applies different styling to cross-KB edges."""
        _, js = self._get_html(f"{graph_server}/graph.js")
        assert "nodeKb[s] !== nodeKb[t]" in js

    def _get_html(self, url):
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, resp.read().decode()

# ---------------------------------------------------------------------------
# Exclusion: junk directories should not appear in graph
# ---------------------------------------------------------------------------

class TestGraphExclusion:
    def test_venv_files_excluded(self, graph_project):
        """Files under .venv should not appear as graph nodes."""
        venv = graph_project / "knowledge" / ".venv"
        venv.mkdir(parents=True)
        (venv / "readme.md").write_text("---\nname: Junk\n---\n")
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        ids = {n["id"] for n in g["nodes"]}
        assert not any(".venv" in nid for nid in ids)

    def test_pycache_files_excluded(self, graph_project):
        """Files under __pycache__ should not appear as graph nodes."""
        cache = graph_project / "knowledge" / "tools" / "__pycache__"
        cache.mkdir(parents=True)
        (cache / "stale.md").write_text("---\nname: Stale\n---\n")
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        ids = {n["id"] for n in g["nodes"]}
        assert not any("__pycache__" in nid for nid in ids)

    def test_pytest_cache_excluded(self, graph_project):
        """Files under __pytest_cache__ should not appear as graph nodes."""
        cache = graph_project / "knowledge" / "__pytest_cache__"
        cache.mkdir(parents=True)
        (cache / "readme.md").write_text("---\nname: Cache\n---\n")
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        ids = {n["id"] for n in g["nodes"]}
        assert not any("__pytest_cache__" in nid for nid in ids)

    def test_valid_files_still_included(self, graph_project):
        """Normal topic files are not affected by exclusion."""
        config = load_config(str(graph_project))
        g = build_graph(str(graph_project), config)
        ids = {n["id"] for n in g["nodes"]}
        assert any("tools/index.md" in nid for nid in ids)
        assert any("editors.md" in nid for nid in ids)

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
