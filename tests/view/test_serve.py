#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pytest"]
# ///
"""Tests for KB Viewer serve.py — unit + integration."""

import json
import os
import re
import threading
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure serve module is importable
from serve import (
    KBViewerHandler,
    _should_skip,
    create_server,
    fuzzy_match,
    is_safe_path,
    load_config,
    load_global_config,
    resolve_cross_kb_links,
    resolve_kb_path,
    strip_frontmatter,
)

# ---------------------------------------------------------------------------
# Unit tests: strip_frontmatter
# ---------------------------------------------------------------------------

class TestStripFrontmatter:
    def test_basic(self):
        content = "---\nname: Hello\ndescription: World\n---\n\n# Body"
        meta, body = strip_frontmatter(content)
        assert meta["name"] == "Hello"
        assert meta["description"] == "World"
        assert body.strip() == "# Body"

    def test_no_frontmatter(self):
        content = "# Just a heading\n\nSome text."
        meta, body = strip_frontmatter(content)
        assert meta == {}
        assert body == content

    def test_empty_string(self):
        meta, body = strip_frontmatter("")
        assert meta == {}
        assert body == ""

    def test_unclosed_frontmatter(self):
        content = "---\nname: Broken\nno closing delimiter"
        meta, body = strip_frontmatter(content)
        assert meta == {}
        assert body == content

    def test_quoted_values(self):
        content = '---\nname: "Quoted Name"\ndescription: \'Single\'\n---\nBody'
        meta, body = strip_frontmatter(content)
        assert meta["name"] == "Quoted Name"
        assert meta["description"] == "Single"

    def test_multiline_body(self):
        content = "---\nname: Test\n---\nLine 1\nLine 2\nLine 3"
        meta, body = strip_frontmatter(content)
        assert meta["name"] == "Test"
        assert "Line 1\nLine 2\nLine 3" == body

    def test_hyphenated_keys(self):
        content = "---\nargument-hint: some hint\n---\nBody"
        meta, body = strip_frontmatter(content)
        assert meta["argument-hint"] == "some hint"

# ---------------------------------------------------------------------------
# Unit tests: resolve_kb_path
# ---------------------------------------------------------------------------

class TestResolveKbPath:
    CONFIG = {"kb_roots": [
        {"name": "core", "path": "./knowledge"},
        {"name": "ios", "path": "./ios/knowledge"},
    ]}

    def test_found(self):
        assert resolve_kb_path(self.CONFIG, "core") == "./knowledge"
        assert resolve_kb_path(self.CONFIG, "ios") == "./ios/knowledge"

    def test_not_found(self):
        assert resolve_kb_path(self.CONFIG, "unknown") is None

    def test_empty_config(self):
        assert resolve_kb_path({"kb_roots": []}, "core") is None
        assert resolve_kb_path({}, "core") is None

# ---------------------------------------------------------------------------
# Unit tests: resolve_cross_kb_links
# ---------------------------------------------------------------------------

class TestResolveCrossKbLinks:
    CONFIG = {"kb_roots": [
        {"name": "core", "path": "./knowledge"},
        {"name": "ios", "path": "./ios/knowledge"},
    ]}

    def test_basic_resolution(self):
        md = "[iOS Topic](@ios/topic/note.md)"
        result = resolve_cross_kb_links(md, self.CONFIG)
        assert result == "[iOS Topic](./ios/knowledge/topic/note.md)"

    def test_unknown_kb_unchanged(self):
        md = "[Unknown](@nope/note.md)"
        result = resolve_cross_kb_links(md, self.CONFIG)
        assert result == md

    def test_multiple_links(self):
        md = "See [@core/a.md](@core/a.md) and [@ios/b.md](@ios/b.md)."
        result = resolve_cross_kb_links(md, self.CONFIG)
        # Link text stays as-is, only hrefs are resolved
        assert "(./knowledge/a.md)" in result
        assert "(./ios/knowledge/b.md)" in result
        assert "(@core/" not in result
        assert "(@ios/" not in result

    def test_no_cross_kb_links(self):
        md = "[local](./note.md)"
        result = resolve_cross_kb_links(md, self.CONFIG)
        assert result == md

    def test_empty_config(self):
        md = "[ref](@core/note.md)"
        result = resolve_cross_kb_links(md, {}, )
        assert result == md

# ---------------------------------------------------------------------------
# Unit tests: fuzzy_match
# ---------------------------------------------------------------------------

class TestFuzzyMatch:
    def test_exact_match(self):
        assert fuzzy_match("skill", "skill") == 0

    def test_exact_case_insensitive(self):
        assert fuzzy_match("SKILL", "skill") == 0
        assert fuzzy_match("skill", "SKILL") == 0

    def test_empty_query(self):
        assert fuzzy_match("", "anything") == 0

    def test_query_longer_than_candidate(self):
        assert fuzzy_match("longquery", "short") is None

    def test_no_subsequence(self):
        assert fuzzy_match("xyz", "hello") is None

    def test_sqkiall_beats_skaaaill(self):
        """User's example: Sqkiall should rank higher (lower gap) than skaaaill."""
        score_a = fuzzy_match("SKILL", "Sqkiall")
        score_b = fuzzy_match("SKILL", "skaaaill")
        assert score_a is not None
        assert score_b is not None
        assert score_a < score_b

    def test_gap_scoring(self):
        # "sXkill" — 1 char gap between s and k
        assert fuzzy_match("skill", "sXkill") == 1

    def test_prefix_match(self):
        assert fuzzy_match("ski", "skill") == 0

    def test_suffix_match(self):
        assert fuzzy_match("ill", "skill") == 0

    def test_scattered(self):
        assert fuzzy_match("skill", "s___k___i___l___l") == 12
        assert fuzzy_match("skill", "s______k______i______l______l") == 24

    def test_finds_shortest_window(self):
        # "aXXab" — greedy leftmost would give gap 3, but shortest window is "ab" at end
        assert fuzzy_match("ab", "aXXab") == 0

    def test_single_char(self):
        assert fuzzy_match("a", "banana") == 0

    def test_repeated_chars(self):
        assert fuzzy_match("aa", "abba") == 2  # a(0), a(3) — gap of 2
        assert fuzzy_match("aa", "aXa") == 1
        assert fuzzy_match("aa", "aa") == 0

    def test_real_note_names(self):
        # Realistic KB searches
        assert fuzzy_match("hook", "Claude Hooks") is not None
        assert fuzzy_match("mcp", "MCP Overview") is not None
        assert fuzzy_match("grok", "Grok Image Prompting") is not None
        assert fuzzy_match("nav", "Swift Navigation") is not None

# ---------------------------------------------------------------------------
# Unit tests: is_safe_path
# ---------------------------------------------------------------------------

class TestIsSafePath:
    def test_safe_relative(self, tmp_path):
        root = str(tmp_path)
        assert is_safe_path(root, "knowledge/note.md") is True

    def test_traversal_blocked(self, tmp_path):
        root = str(tmp_path)
        assert is_safe_path(root, "../../etc/passwd") is False

    def test_absolute_outside(self, tmp_path):
        root = str(tmp_path)
        assert is_safe_path(root, "/etc/passwd") is False

    def test_nested_safe(self, tmp_path):
        root = str(tmp_path)
        assert is_safe_path(root, "a/../b/note.md") is True

# ---------------------------------------------------------------------------
# Unit tests: load_config
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_valid_config(self, tmp_path):
        config_dir = tmp_path / ".claude" / "knowledge-base"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({
            "kb_roots": [{"name": "test", "path": "./kb"}]
        }))
        result = load_config(str(tmp_path))
        assert len(result["kb_roots"]) == 1
        assert result["kb_roots"][0]["name"] == "test"

    def test_missing_config(self, tmp_path):
        result = load_config(str(tmp_path))
        assert result == {"kb_roots": []}

    def test_empty_config(self, tmp_path):
        config_dir = tmp_path / ".claude" / "knowledge-base"
        config_dir.mkdir(parents=True)
        (config_dir / "config.json").write_text('{"kb_roots": []}')
        result = load_config(str(tmp_path))
        assert result["kb_roots"] == []

# ---------------------------------------------------------------------------
# Unit tests: slugify (mirrors client-side JS slugify for header anchors)
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """Python mirror of the JS slugify in index.html."""
    s = text.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")

class TestSlugify:
    def test_basic(self):
        assert slugify("Aurora Model Architecture") == "aurora-model-architecture"

    def test_already_slug(self):
        assert slugify("caching") == "caching"

    def test_special_chars(self):
        assert slugify("Grok vs Gemini (Comparison)") == "grok-vs-gemini-comparison"

    def test_multiple_spaces(self):
        assert slugify("Seed  Values   and Reproducibility") == "seed-values-and-reproducibility"

    def test_leading_trailing(self):
        assert slugify("  Hello World  ") == "hello-world"

    def test_numbers(self):
        assert slugify("Technique 1: Trait-locking") == "technique-1-trait-locking"

    def test_empty(self):
        assert slugify("") == ""

class TestAnchorHeaderConsistency:
    """Verify that ](#slug) anchor links in markdown resolve to actual headers via slugify."""

    @staticmethod
    def _extract_anchors(body: str) -> list[str]:
        """Extract all ](#slug) anchors from markdown body."""
        return re.findall(r"\]\(#([^)]+)\)", body)

    @staticmethod
    def _extract_headers(body: str) -> list[str]:
        """Extract all markdown headers and slugify them."""
        headers = re.findall(r"^(#{1,6})\s+(.+)$", body, re.MULTILINE)
        return [slugify(text) for _, text in headers]

    def test_anchors_match_headers_simple(self):
        body = (
            "## Contents\n\n"
            "- [Caching](#caching)\n"
            "- [Scaling](#scaling)\n\n"
            "## Caching\n\nCache stuff.\n\n"
            "## Scaling\n\nScale stuff."
        )
        anchors = self._extract_anchors(body)
        headers = self._extract_headers(body)
        for anchor in anchors:
            assert anchor in headers, f"Anchor #{anchor} has no matching header"

    def test_anchors_match_headers_mixed_levels(self):
        body = (
            "- [Intro](#intro)\n"
            "- [Sub Topic](#sub-topic)\n\n"
            "# Intro\n\nHello.\n\n"
            "### Sub Topic\n\nDetails."
        )
        anchors = self._extract_anchors(body)
        headers = self._extract_headers(body)
        for anchor in anchors:
            assert anchor in headers, f"Anchor #{anchor} has no matching header"

    def test_unmatched_anchor_detected(self):
        body = "- [Missing](#nonexistent)\n\n## Actual Header\n\nText."
        anchors = self._extract_anchors(body)
        headers = self._extract_headers(body)
        assert "nonexistent" not in headers

@pytest.fixture(scope="session")
def toggle_server(tmp_path_factory):
    """Server for source toggle contract tests."""
    tmp_path = tmp_path_factory.mktemp("toggle")
    config_dir = tmp_path / ".claude" / "knowledge-base"
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text(json.dumps({
        "kb_roots": [{"name": "t", "path": "./kb"}]
    }))
    kb = tmp_path / "kb" / "demo"
    kb.mkdir(parents=True)
    (kb / "index.md").write_text(
        "---\nname: Toggle Test\ndescription: For toggle\n---\n\n"
        "# Heading\n\nParagraph one.\n\n## Section\n\nParagraph two."
    )
    (tmp_path / "kb" / "note.md").write_text(
        "---\nname: Original\ndescription: Test\n---\n\n# Content\n\nBody text."
    )
    viewer_dir = str(Path(__file__).resolve().parent.parent.parent / "knowledge" / "view" / "skill" / "scripts")
    server = create_server(0, str(tmp_path), viewer_dir)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()

class TestSourceToggleContract:
    """Verify server returns both meta and body so client can build source view."""

    def test_file_returns_meta_and_body(self, toggle_server):
        """File API returns separate meta + body for source/rendered toggle."""
        url = f"{toggle_server}/api/file?path=kb/demo/index.md"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        # Meta is returned separately (client reconstructs frontmatter for source)
        assert "name" in data["meta"]
        assert data["meta"]["name"] == "Toggle Test"
        # Body has no frontmatter delimiters
        assert "---" not in data["body"]
        # Body has real content (needed for height ratio calculation)
        assert len(data["body"].strip()) > 50
        # Client can reconstruct: "---\nkey: val\n---\n\n" + body
        reconstructed = "---\n"
        for k, v in data["meta"].items():
            reconstructed += f"{k}: {v}\n"
        reconstructed += "---\n\n" + data["body"]
        assert "name: Toggle Test" in reconstructed
        assert "# Heading" in reconstructed

    def test_source_reconstruction_matches_original(self, toggle_server):
        """Reconstructed source from meta+body matches original file content."""
        url = f"{toggle_server}/api/file?path=kb/note.md"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        reconstructed = "---\n"
        for k, v in data["meta"].items():
            reconstructed += f"{k}: {v}\n"
        reconstructed += "---\n\n" + data["body"]
        # Should contain all key parts of the original
        assert "name: Original" in reconstructed
        assert "description: Test" in reconstructed
        assert "# Content" in reconstructed
        assert "Body text." in reconstructed

# ---------------------------------------------------------------------------
# Integration tests: HTTP server
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_project(tmp_path_factory):
    """Set up a minimal KB project for integration tests."""
    tmp_path = tmp_path_factory.mktemp("test_project")
    # Config
    config_dir = tmp_path / ".claude" / "knowledge-base"
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text(json.dumps({
        "kb_roots": [{"name": "test", "path": "./kb"}]
    }))

    # KB with a topic note
    topics = tmp_path / "kb" / "demo"
    topics.mkdir(parents=True)
    (topics / "index.md").write_text(
        "---\nname: Demo Index\ndescription: Demo topic\n---\n\n# Demo\n\nHello world."
    )
    (topics / "note.md").write_text(
        "---\nname: Sample Note\ndescription: A sample\n---\n\n# Sample\n\nContent with [link](../demo/index.md)."
    )

    return tmp_path

@pytest.fixture(scope="session")
def server_url(test_project):
    """Start a test server on a random port, yield its URL, then shut down."""
    viewer_dir = str(Path(__file__).resolve().parent.parent.parent / "knowledge" / "view" / "skill" / "scripts")
    server = create_server(0, str(test_project), viewer_dir)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()

class TestHTTPEndpoints:
    def _get(self, url):
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())

    def _get_html(self, url):
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read().decode()

    def test_index_html(self, server_url):
        status, body = self._get_html(f"{server_url}/")
        assert status == 200
        assert "KB Viewer" in body

    def test_config_endpoint(self, server_url):
        status, data = self._get(f"{server_url}/api/config")
        assert status == 200
        assert "kb_roots" in data

    def test_file_endpoint(self, server_url):
        status, data = self._get(f"{server_url}/api/file?path=kb/demo/index.md")
        assert status == 200
        assert data["meta"]["name"] == "Demo Index"
        assert "Hello world" in data["body"]

    def test_file_endpoint_strips_frontmatter(self, server_url):
        status, data = self._get(f"{server_url}/api/file?path=kb/demo/note.md")
        assert status == 200
        assert "---" not in data["body"]
        assert data["meta"]["name"] == "Sample Note"

    def test_file_not_found(self, server_url):
        try:
            self._get(f"{server_url}/api/file?path=nonexistent.md")
            assert False, "Expected 404"
        except urllib.error.HTTPError as e:
            assert e.code == 404

    def test_path_traversal_blocked(self, server_url):
        try:
            self._get(f"{server_url}/api/file?path=../../etc/passwd")
            assert False, "Expected 403"
        except urllib.error.HTTPError as e:
            assert e.code == 403

    def test_missing_path_param(self, server_url):
        try:
            self._get(f"{server_url}/api/file")
            assert False, "Expected 400"
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_spa_fallback_serves_html(self, server_url):
        """Unknown routes serve index.html for client-side routing."""
        status, html = self._get_html(f"{server_url}/nonexistent")
        assert status == 200
        assert "KB Viewer" in html

    def test_spa_fallback_kb_named_path(self, server_url):
        """URL with KB name prefix serves index.html for client routing."""
        status, html = self._get_html(f"{server_url}/test/demo/index.md")
        assert status == 200
        assert "KB Viewer" in html

    def test_spa_fallback_nested_path(self, server_url):
        """Deeply nested paths still serve index.html."""
        status, html = self._get_html(f"{server_url}/test/a/b/c/note.md")
        assert status == 200
        assert "KB Viewer" in html

    def test_spa_fallback_with_fragment(self, server_url):
        """Paths that browsers would send (without #fragment) still work."""
        # Browsers strip #fragments before sending, so server just sees the path
        status, html = self._get_html(f"{server_url}/test/demo/index.md")
        assert status == 200
        assert "KB Viewer" in html

    def test_spa_fallback_folder_path_no_trailing_slash(self, server_url):
        """Folder-like URL without .md serves index.html for client redirect."""
        status, html = self._get_html(f"{server_url}/test/demo")
        assert status == 200
        assert "KB Viewer" in html

    def test_spa_fallback_folder_path_trailing_slash(self, server_url):
        """Folder-like URL with trailing slash serves index.html."""
        status, html = self._get_html(f"{server_url}/test/demo/")
        assert status == 200
        assert "KB Viewer" in html

    def test_folder_path_index_accessible(self, server_url):
        """The index.md that a folder URL would redirect to is loadable via API."""
        # Client boot() appends /index.md to folder paths; verify the target exists
        status, data = self._get(
            f"{server_url}/api/file?path=kb/demo/index.md"
        )
        assert status == 200
        assert data["meta"]["name"] == "Demo Index"

    def test_api_routes_not_affected_by_spa_fallback(self, server_url):
        """API routes still return JSON, not index.html."""
        status, data = self._get(f"{server_url}/api/config")
        assert status == 200
        assert "kb_roots" in data

        status, data = self._get(f"{server_url}/api/search?q=Demo")
        assert status == 200
        assert "results" in data

    def test_search_missing_query(self, server_url):
        try:
            self._get(f"{server_url}/api/search")
            assert False, "Expected 400"
        except urllib.error.HTTPError as e:
            assert e.code == 400

    def test_search_returns_results(self, server_url):
        status, data = self._get(f"{server_url}/api/search?q=Demo")
        assert status == 200
        assert "results" in data
        assert len(data["results"]) > 0
        assert data["results"][0]["name"] == "Demo Index"

    def test_search_no_match(self, server_url):
        status, data = self._get(f"{server_url}/api/search?q=zzzzzznothing")
        assert status == 200
        assert data["results"] == []

    def test_search_ranked_by_gap(self, server_url):
        status, data = self._get(f"{server_url}/api/search?q=Sample")
        assert status == 200
        results = data["results"]
        # Results should be sorted by score ascending
        for i in range(len(results) - 1):
            assert results[i]["score"] <= results[i + 1]["score"]

# ---------------------------------------------------------------------------
# Multi-KB integration tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def multi_kb_project(tmp_path_factory):
    """Set up a project with two KBs for multi-KB testing."""
    tmp_path = tmp_path_factory.mktemp("multi_kb")
    config_dir = tmp_path / ".claude" / "knowledge-base"
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text(json.dumps({
        "kb_roots": [
            {"name": "core", "path": "./knowledge"},
            {"name": "mobile", "path": "./mobile/knowledge"},
        ]
    }))

    # Core KB
    core = tmp_path / "knowledge" 
    (core / "systems").mkdir(parents=True)
    (core / "index.md").write_text(
        "---\nname: Core Root\ndescription: Core KB root\n---\n\n# Core\n\n"
        "- [Systems](systems/index.md)\n"
    )
    (core / "systems" / "index.md").write_text(
        "---\nname: Systems\ndescription: System design\n---\n\n# Systems\n\n"
        "## Contents\n\n- [Caching](#caching)\n\n## Caching\n\nCache strategies."
    )
    (core / "systems" / "scaling.md").write_text(
        "---\nname: Scaling\ndescription: Scaling patterns\n---\n\n# Scaling\n\nSee [index](index.md)."
    )

    # Mobile KB
    mobile = tmp_path / "mobile" / "knowledge" 
    (mobile / "swift").mkdir(parents=True)
    (mobile / "index.md").write_text(
        "---\nname: Mobile Root\ndescription: Mobile KB root\n---\n\n# Mobile\n\n"
        "- [Swift](swift/index.md)\n"
        "- [Core link](@core/systems/index.md)\n"
    )
    (mobile / "swift" / "index.md").write_text(
        "---\nname: Swift\ndescription: Swift language\n---\n\n# Swift\n\nSwift notes."
    )

    return tmp_path

@pytest.fixture(scope="session")
def multi_kb_url(multi_kb_project):
    """Start a test server for multi-KB project."""
    viewer_dir = str(Path(__file__).resolve().parent.parent.parent / "knowledge" / "view" / "skill" / "scripts")
    server = create_server(0, str(multi_kb_project), viewer_dir)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()

class TestMultiKB:
    def _get(self, url):
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())

    def _get_html(self, url):
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read().decode()

    def test_config_lists_both_kbs(self, multi_kb_url):
        status, data = self._get(f"{multi_kb_url}/api/config")
        assert status == 200
        names = [e["name"] for e in data["kb_roots"]]
        assert "core" in names
        assert "mobile" in names

    def test_file_from_core_kb(self, multi_kb_url):
        status, data = self._get(
            f"{multi_kb_url}/api/file?path=knowledge/systems/index.md"
        )
        assert status == 200
        assert data["meta"]["name"] == "Systems"

    def test_file_from_mobile_kb(self, multi_kb_url):
        status, data = self._get(
            f"{multi_kb_url}/api/file?path=mobile/knowledge/swift/index.md"
        )
        assert status == 200
        assert data["meta"]["name"] == "Swift"

    def test_cross_kb_links_resolved(self, multi_kb_url):
        """@core/... links in mobile KB should resolve to filesystem paths."""
        status, data = self._get(
            f"{multi_kb_url}/api/file?path=mobile/knowledge/index.md"
        )
        assert status == 200
        assert "@core/" not in data["body"]
        assert "./knowledge/systems/index.md" in data["body"]

    def test_cross_kb_resolved_path_is_loadable(self, multi_kb_url):
        """Resolved @core/... path (./knowledge/...) should be loadable via file API."""
        # Mobile index has @core link that server resolves to ./knowledge/...
        _, data = self._get(
            f"{multi_kb_url}/api/file?path=mobile/knowledge/index.md"
        )
        # Extract the resolved path from the body
        import re
        match = re.search(r"\((\./knowledge/[^)]+)\)", data["body"])
        assert match, "Expected resolved cross-KB link in body"
        resolved_path = match.group(1)
        # Client click handler uses this path directly (starts with ./)
        status, target = self._get(
            f"{multi_kb_url}/api/file?path={resolved_path}"
        )
        assert status == 200
        assert target["meta"]["name"] == "Systems"

    def test_cross_kb_reverse_link_resolvable(self, multi_kb_url):
        """A @mobile/... link from core KB should resolve and be loadable."""
        # Add reverse test: simulate what server would do with @mobile link
        # resolve_cross_kb_links maps @mobile/path → ./mobile/knowledge/path
        _, config = self._get(f"{multi_kb_url}/api/config")
        mobile_cfg = next(e for e in config["kb_roots"] if e["name"] == "mobile")
        # Simulated resolved path: ./mobile/knowledge/swift/index.md
        resolved = f"{mobile_cfg['path']}/swift/index.md"
        status, data = self._get(
            f"{multi_kb_url}/api/file?path={resolved}"
        )
        assert status == 200
        assert data["meta"]["name"] == "Swift"

    def test_search_spans_both_kbs(self, multi_kb_url):
        """Search should find notes from both KBs."""
        _, data = self._get(f"{multi_kb_url}/api/search?q=Systems")
        core_hit = any(r["kb"] == "core" for r in data["results"])
        assert core_hit

        _, data = self._get(f"{multi_kb_url}/api/search?q=Swift")
        mobile_hit = any(r["kb"] == "mobile" for r in data["results"])
        assert mobile_hit

    def test_spa_fallback_core_path(self, multi_kb_url):
        """URL with core KB name serves index.html."""
        status, html = self._get_html(
            f"{multi_kb_url}/core/systems/index.md"
        )
        assert status == 200
        assert "KB Viewer" in html

    def test_spa_fallback_mobile_path(self, multi_kb_url):
        """URL with mobile KB name serves index.html."""
        status, html = self._get_html(
            f"{multi_kb_url}/mobile/swift/index.md"
        )
        assert status == 200
        assert "KB Viewer" in html

    def test_spa_fallback_folder_path_core(self, multi_kb_url):
        """Folder URL for core KB serves index.html for client redirect."""
        status, html = self._get_html(
            f"{multi_kb_url}/core/systems"
        )
        assert status == 200
        assert "KB Viewer" in html

    def test_spa_fallback_folder_path_mobile(self, multi_kb_url):
        """Folder URL for mobile KB serves index.html for client redirect."""
        status, html = self._get_html(
            f"{multi_kb_url}/mobile/swift/"
        )
        assert status == 200
        assert "KB Viewer" in html

    def test_folder_to_index_roundtrip(self, multi_kb_url):
        """Simulates client boot: folder URL → append index.md → fromUrlPath → file API."""
        _, config = self._get(f"{multi_kb_url}/api/config")
        # Client sees URL "/core/systems", appends "/index.md"
        url_path = "core/systems/index.md"
        core_cfg = next(e for e in config["kb_roots"] if e["name"] == "core")
        fs_path = core_cfg["path"] + url_path[len("core"):]
        status, data = self._get(
            f"{multi_kb_url}/api/file?path={fs_path}"
        )
        assert status == 200
        assert data["meta"]["name"] == "Systems"

    def test_internal_link_target_accessible(self, multi_kb_url):
        """File referenced by an internal .md link should be loadable."""
        # scaling.md links to index.md — resolve and verify target exists
        _, data = self._get(
            f"{multi_kb_url}/api/file?path=knowledge/systems/scaling.md"
        )
        assert "index.md" in data["body"]
        # The resolved target should be accessible
        _, target = self._get(
            f"{multi_kb_url}/api/file?path=knowledge/systems/index.md"
        )
        assert target["meta"]["name"] == "Systems"

    def test_anchor_link_in_content(self, multi_kb_url):
        """File with #anchor links should have matching header IDs in markdown."""
        _, data = self._get(
            f"{multi_kb_url}/api/file?path=knowledge/systems/index.md"
        )
        # Body has [Caching](#caching) and ## Caching header
        assert "#caching" in data["body"]
        assert "## Caching" in data["body"]

    def test_anchor_slugs_match_headers(self, multi_kb_url):
        """Every ](#slug) anchor in a doc should match a slugified header."""
        _, data = self._get(
            f"{multi_kb_url}/api/file?path=knowledge/systems/index.md"
        )
        body = data["body"]
        anchors = re.findall(r"\]\(#([^)]+)\)", body)
        headers = re.findall(r"^#{1,6}\s+(.+)$", body, re.MULTILINE)
        header_slugs = {slugify(h) for h in headers}
        for anchor in anchors:
            assert anchor in header_slugs, (
                f"Anchor #{anchor} has no matching header. "
                f"Available: {header_slugs}"
            )

    def test_html_has_internal_link_markers(self, multi_kb_url):
        """Served HTML should use data-href for internal links (not raw href)."""
        status, html = self._get_html(f"{multi_kb_url}/")
        assert status == 200
        assert "data-href" in html

    def test_config_paths_have_dot_slash_prefix(self, multi_kb_url):
        """Config paths use ./ prefix — client fromUrlPath must preserve this."""
        _, config = self._get(f"{multi_kb_url}/api/config")
        core_cfg = next(e for e in config["kb_roots"] if e["name"] == "core")
        assert core_cfg["path"].startswith("./"), (
            f"Config path '{core_cfg['path']}' should start with ./"
        )

    def test_file_api_accepts_dot_slash_prefix(self, multi_kb_url):
        """File API accepts paths with ./ prefix (format fromUrlPath produces)."""
        # Simulate what fromUrlPath returns: config path + URL suffix
        # URL: core/systems/index.md → ./knowledge/systems/index.md
        status, data = self._get(
            f"{multi_kb_url}/api/file?path=./knowledge/systems/index.md"
        )
        assert status == 200
        assert data["meta"]["name"] == "Systems"

    def test_url_to_fs_path_roundtrip(self, multi_kb_url):
        """Simulates client fromUrlPath: URL path → config-prefixed fs path → file API."""
        _, config = self._get(f"{multi_kb_url}/api/config")

        # For each KB, simulate the fromUrlPath mapping and verify file API works
        test_cases = [
            ("core", "core/systems/index.md", "Systems"),
            ("mobile", "mobile/swift/index.md", "Swift"),
        ]
        for kb_name, url_path, expected_name in test_cases:
            cfg = next(e for e in config["kb_roots"] if e["name"] == kb_name)
            # Client fromUrlPath: entry.path + urlPath.slice(entry.name.length)
            fs_path = cfg["path"] + url_path[len(kb_name):]
            status, data = self._get(
                f"{multi_kb_url}/api/file?path={fs_path}"
            )
            assert status == 200, f"Failed for {kb_name}: {fs_path}"
            assert data["meta"]["name"] == expected_name

# ---------------------------------------------------------------------------
# Unit tests: _should_skip
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Unit + integration tests: tree endpoint (kb_loader auto-detect)
# ---------------------------------------------------------------------------

class TestTreeEndpoint:
    """Guard against regressions in serve.py's kb_loader invocation."""

    def test_serve_tree_calls_kb_loader_without_legacy_flags(self, tmp_path):
        """_serve_tree must call kb_loader without removed --kb/--kb-name flags."""
        # Use isolated tmp_path to avoid mutating session-scoped test_project
        config_dir = tmp_path / ".claude" / "knowledge-base"
        config_dir.mkdir(parents=True)
        (config_dir / "config.json").write_text(json.dumps({
            "kb_roots": [{"name": "test", "path": "./kb"}]
        }))
        kb_topics = tmp_path / "kb" / "demo"
        kb_topics.mkdir(parents=True)
        (kb_topics / "index.md").write_text("---\nname: Demo\n---\n\n# Demo")
        # Place a fake kb_loader.py so _find_kb_loader finds it
        kb_dir = tmp_path / "kb" / "finding" / "skill" / "scripts"
        kb_dir.mkdir(parents=True, exist_ok=True)
        (kb_dir / "kb_loader.py").write_text("# stub")

        viewer_dir = str(Path(__file__).resolve().parent.parent.parent / "knowledge" / "view" / "skill" / "scripts")
        server = create_server(0, str(tmp_path), viewer_dir)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            import subprocess as sp
            original_run = sp.run
            captured_cmds = []

            def spy_run(cmd, *args, **kwargs):
                captured_cmds.append(list(cmd))
                # Return a fake success so the endpoint responds
                return type(original_run(["true"], capture_output=True))(
                    args=cmd, returncode=0,
                    stdout='{"kbs": []}', stderr=""
                )

            with patch("serve.subprocess.run", side_effect=spy_run):
                url = f"http://127.0.0.1:{port}/api/tree"
                with urllib.request.urlopen(url, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                    assert data == {"kbs": []}

            kb_loader_cmds = [c for c in captured_cmds if any("kb_loader" in str(a) for a in c)]
            assert len(kb_loader_cmds) > 0, "Expected _serve_tree to call kb_loader"
            cmd = kb_loader_cmds[0]
            assert "--kb" not in cmd, (
                f"serve.py must not pass removed --kb flag. Got: {cmd}"
            )
            assert "--kb-name" not in cmd, (
                f"serve.py must not pass removed --kb-name flag. Got: {cmd}"
            )
        finally:
            server.shutdown()

    def test_tree_endpoint_returns_valid_json(self, server_url):
        """GET /api/tree should return valid JSON, HTTP error, or empty (no kb_loader)."""
        try:
            req = urllib.request.Request(f"{server_url}/api/tree")
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode()
                if body:
                    data = json.loads(body)
                    assert isinstance(data, dict)
                # Empty body is acceptable when kb_loader is not found
        except urllib.error.HTTPError as e:
            # 500 is acceptable if kb_loader not found in test project
            assert e.code == 500

# ---------------------------------------------------------------------------
# Unit tests: _find_kb_loader layouts
# ---------------------------------------------------------------------------

class TestFindKbLoader:
    """_find_kb_loader must resolve kb_loader.py across install layouts."""

    def _make_handler(self, project_root, config=None):
        """Create a minimal handler instance for testing _find_kb_loader."""
        handler = object.__new__(KBViewerHandler)
        handler.project_root = str(project_root)
        handler.kb_config = config or {"kb_roots": []}
        return handler

    def test_source_repo_layout(self, tmp_path):
        """find/skill/scripts/kb_loader.py relative to view/skill/scripts/serve.py."""
        view_scripts = tmp_path / "knowledge" / "view" / "skill" / "scripts"
        view_scripts.mkdir(parents=True)
        find_scripts = tmp_path / "knowledge" / "find" / "skill" / "scripts"
        find_scripts.mkdir(parents=True)
        (find_scripts / "kb_loader.py").write_text("# stub")

        handler = self._make_handler(tmp_path)
        with patch("serve.__file__", str(view_scripts / "serve.py")):
            result = handler._find_kb_loader()
        assert result is not None
        assert result.name == "kb_loader.py"
        assert "find" in str(result)

    def test_claude_skills_sibling_layout(self, tmp_path):
        """kb-find sibling under .claude/skills/."""
        view_scripts = tmp_path / ".claude" / "skills" / "kb-view" / "scripts"
        view_scripts.mkdir(parents=True)
        find_scripts = tmp_path / ".claude" / "skills" / "kb-find" / "scripts"
        find_scripts.mkdir(parents=True)
        (find_scripts / "kb_loader.py").write_text("# stub")

        handler = self._make_handler(tmp_path)
        with patch("serve.__file__", str(view_scripts / "serve.py")):
            result = handler._find_kb_loader()
        assert result is not None
        assert result.name == "kb_loader.py"

    def test_plugin_layout(self, tmp_path):
        """skills/find/scripts/ sibling under plugin cache."""
        view_scripts = tmp_path / "skills" / "view" / "scripts"
        view_scripts.mkdir(parents=True)
        find_scripts = tmp_path / "skills" / "find" / "scripts"
        find_scripts.mkdir(parents=True)
        (find_scripts / "kb_loader.py").write_text("# stub")

        handler = self._make_handler(tmp_path)
        with patch("serve.__file__", str(view_scripts / "serve.py")):
            result = handler._find_kb_loader()
        assert result is not None
        assert result.name == "kb_loader.py"

    def test_fallback_to_kb_roots_rglob(self, tmp_path):
        """Falls back to searching inside kb_roots when sibling paths fail."""
        config_dir = tmp_path / ".claude" / "knowledge-base"
        config_dir.mkdir(parents=True)
        (config_dir / "config.json").write_text(json.dumps({
            "kb_roots": [{"name": "core", "path": "./kb"}]
        }))
        kb_scripts = tmp_path / "kb" / "finding" / "skill" / "scripts"
        kb_scripts.mkdir(parents=True)
        (kb_scripts / "kb_loader.py").write_text("# stub")

        handler = self._make_handler(tmp_path, load_config(str(tmp_path)))
        # Patch __file__ to a location where no sibling paths exist
        with patch("serve.__file__", str(tmp_path / "nowhere" / "serve.py")):
            result = handler._find_kb_loader()
        assert result is not None
        assert result.name == "kb_loader.py"

    def test_returns_none_when_not_found(self, tmp_path):
        """Returns None when kb_loader.py doesn't exist anywhere."""
        handler = self._make_handler(tmp_path)
        with patch("serve.__file__", str(tmp_path / "nowhere" / "serve.py")):
            result = handler._find_kb_loader()
        assert result is None

# ---------------------------------------------------------------------------
# Unit tests: _should_skip
# ---------------------------------------------------------------------------

class TestShouldSkip:
    def test_dot_prefixed_dir(self):
        root = Path("/project")
        assert _should_skip(Path("/project/.venv/lib/readme.md"), root)

    def test_pycharm_dir(self):
        root = Path("/project")
        assert _should_skip(Path("/project/.pycharm/config.md"), root)

    def test_dunder_pycache(self):
        root = Path("/project")
        assert _should_skip(Path("/project/__pycache__/cached.md"), root)

    def test_dunder_pytest_cache(self):
        root = Path("/project")
        assert _should_skip(Path("/project/__pytest_cache__/readme.md"), root)

    def test_nested_dunder_dir(self):
        root = Path("/project")
        assert _should_skip(Path("/project/topic/__pycache__/x.md"), root)

    def test_valid_path_not_skipped(self):
        root = Path("/project")
        assert not _should_skip(Path("/project/topic/index.md"), root)

    def test_skill_path_not_skipped(self):
        root = Path("/project")
        assert not _should_skip(Path("/project/topic/skill/SKILL.md"), root)

# ---------------------------------------------------------------------------
# Config hot-reload tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def hot_reload_project(tmp_path):
    """Project that starts with one KB; tests add a second KB after server starts."""
    config_dir = tmp_path / ".claude" / "knowledge-base"
    config_dir.mkdir(parents=True)

    # Start with only "alpha" KB
    (config_dir / "config.json").write_text(json.dumps({
        "kb_roots": [{"name": "alpha", "path": "./alpha"}]
    }))

    alpha = tmp_path / "alpha"
    alpha.mkdir()
    (alpha / "index.md").write_text(
        "---\nname: Alpha Root\ndescription: First KB\n---\n\n# Alpha"
    )
    (alpha / "note.md").write_text(
        "---\nname: Alpha Note\n---\n\nSee [root](index.md)."
    )

    # Pre-create "beta" KB files (but not in config yet)
    beta = tmp_path / "beta"
    beta.mkdir()
    (beta / "index.md").write_text(
        "---\nname: Beta Root\ndescription: Second KB\n---\n\n# Beta"
    )
    (beta / "page.md").write_text(
        "---\nname: Beta Page\n---\n\nSee [root](index.md)."
    )

    return tmp_path, config_dir / "config.json"


@pytest.fixture()
def hot_reload_server(hot_reload_project):
    """Server started with only alpha KB."""
    project_path, _ = hot_reload_project
    viewer_dir = str(
        Path(__file__).resolve().parent.parent.parent
        / "knowledge" / "view" / "skill" / "scripts"
    )
    server = create_server(0, str(project_path), viewer_dir)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


class TestConfigHotReload:
    """Config changes on disk are picked up without server restart."""

    def _get(self, url):
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode())

    def test_initial_config_has_one_kb(self, hot_reload_server):
        data = self._get(f"{hot_reload_server}/api/config")
        local = [e for e in data["kb_roots"] if not e.get("readonly")]
        assert len(local) == 1
        assert local[0]["name"] == "alpha"

    def test_initial_graph_has_only_alpha(self, hot_reload_server):
        data = self._get(f"{hot_reload_server}/api/graph")
        kbs = {n["kb"] for n in data["nodes"]}
        assert kbs == {"alpha"}

    def test_added_kb_appears_in_config(self, hot_reload_project, hot_reload_server):
        _, config_file = hot_reload_project
        config_file.write_text(json.dumps({
            "kb_roots": [
                {"name": "alpha", "path": "./alpha"},
                {"name": "beta", "path": "./beta"},
            ]
        }))

        data = self._get(f"{hot_reload_server}/api/config")
        names = [e["name"] for e in data["kb_roots"]]
        assert "alpha" in names
        assert "beta" in names

    def test_added_kb_appears_in_graph(self, hot_reload_project, hot_reload_server):
        _, config_file = hot_reload_project
        config_file.write_text(json.dumps({
            "kb_roots": [
                {"name": "alpha", "path": "./alpha"},
                {"name": "beta", "path": "./beta"},
            ]
        }))

        data = self._get(f"{hot_reload_server}/api/graph")
        kbs = {n["kb"] for n in data["nodes"]}
        assert "alpha" in kbs
        assert "beta" in kbs

    def test_added_kb_appears_in_search(self, hot_reload_project, hot_reload_server):
        _, config_file = hot_reload_project
        config_file.write_text(json.dumps({
            "kb_roots": [
                {"name": "alpha", "path": "./alpha"},
                {"name": "beta", "path": "./beta"},
            ]
        }))

        data = self._get(f"{hot_reload_server}/api/search?q=Beta")
        hits = [r["name"] for r in data["results"]]
        assert "Beta Root" in hits

    def test_no_reload_when_mtime_unchanged(self, hot_reload_project, hot_reload_server):
        """Config is not re-parsed when the file hasn't been modified."""
        # Hit the endpoint twice without changing config — second call should
        # use cached config (verified by patching load_config)
        self._get(f"{hot_reload_server}/api/config")  # prime the mtime

        call_count = 0
        original_load = load_config

        def counting_load(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return original_load(*args, **kwargs)

        with patch("serve.load_config", side_effect=counting_load):
            self._get(f"{hot_reload_server}/api/config")
            self._get(f"{hot_reload_server}/api/config")

        assert call_count == 0, (
            f"load_config called {call_count} times despite unchanged mtime"
        )

    def test_removed_kb_disappears(self, hot_reload_project, hot_reload_server):
        """Removing a KB from config removes it from all endpoints."""
        _, config_file = hot_reload_project

        # First add beta
        config_file.write_text(json.dumps({
            "kb_roots": [
                {"name": "alpha", "path": "./alpha"},
                {"name": "beta", "path": "./beta"},
            ]
        }))
        data = self._get(f"{hot_reload_server}/api/graph")
        assert "beta" in {n["kb"] for n in data["nodes"]}

        # Now remove beta
        config_file.write_text(json.dumps({
            "kb_roots": [{"name": "alpha", "path": "./alpha"}]
        }))
        data = self._get(f"{hot_reload_server}/api/graph")
        assert "beta" not in {n["kb"] for n in data["nodes"]}


# ===================================================================
# Unit tests: is_safe_path with allowed_roots (global KBs)
# ===================================================================

class TestIsSafePathGlobal:
    def test_absolute_path_in_allowed_root(self, tmp_path):
        root = str(tmp_path / "project")
        global_kb = str(tmp_path / "global-kb")
        (tmp_path / "global-kb").mkdir()
        assert is_safe_path(root, f"{global_kb}/note.md", [global_kb]) is True

    def test_absolute_path_outside_all_roots(self, tmp_path):
        root = str(tmp_path / "project")
        global_kb = str(tmp_path / "global-kb")
        assert is_safe_path(root, "/etc/passwd", [global_kb]) is False

    def test_no_allowed_roots_rejects_absolute(self, tmp_path):
        root = str(tmp_path)
        assert is_safe_path(root, "/some/absolute/path") is False

    def test_relative_path_still_works_with_allowed_roots(self, tmp_path):
        root = str(tmp_path)
        assert is_safe_path(root, "knowledge/note.md", ["/other"]) is True

    def test_traversal_not_saved_by_allowed_roots(self, tmp_path):
        root = str(tmp_path / "project")
        assert is_safe_path(root, "../../etc/passwd", ["/other"]) is False


# ===================================================================
# Unit tests: load_global_config (serve.py)
# ===================================================================

class TestLoadGlobalConfigServe:
    def test_returns_none_when_no_global_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert load_global_config() is None

    def test_returns_none_when_no_source(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        cfg_dir = tmp_path / ".claude" / "knowledge-base"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "config.json").write_text(json.dumps({"namespace": "god"}))
        assert load_global_config() is None

    def test_loads_source_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        # Create global config
        cfg_dir = tmp_path / ".claude" / "knowledge-base"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "config.json").write_text(json.dumps({
            "namespace": "god",
            "source": str(tmp_path / "source-project"),
        }))
        # Create source project config
        source_cfg = tmp_path / "source-project" / ".claude" / "knowledge-base"
        source_cfg.mkdir(parents=True)
        (source_cfg / "config.json").write_text(json.dumps({
            "kb_roots": [{"name": "core", "path": "./knowledge"}]
        }))
        result = load_global_config()
        assert result is not None
        assert len(result["kb_roots"]) == 1
        assert result["kb_roots"][0]["name"] == "god.core"
        assert result["kb_roots"][0]["readonly"] is True
        assert result["kb_roots"][0]["path"] == str(tmp_path / "source-project" / "knowledge")


# ===================================================================
# Integration tests: global KB in viewer
# ===================================================================

@pytest.fixture()
def global_kb_project(tmp_path, monkeypatch):
    """Project with local KB + a separate global KB directory."""
    # Local project
    config_dir = tmp_path / "project" / ".claude" / "knowledge-base"
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text(json.dumps({
        "kb_roots": [{"name": "local", "path": "./knowledge"}]
    }))
    local_kb = tmp_path / "project" / "knowledge" / "topic"
    local_kb.mkdir(parents=True)
    (tmp_path / "project" / "knowledge" / "index.md").write_text(
        "---\nname: Local Root\ndescription: Local KB root\n---\n\n# Local"
    )
    (local_kb / "index.md").write_text(
        "---\nname: Local Topic\ndescription: A local topic\n---\n\n# Local Topic\n\nLocal content."
    )

    # Global KB (separate directory, its own config)
    global_project = tmp_path / "god-kb"
    global_cfg = global_project / ".claude" / "knowledge-base"
    global_cfg.mkdir(parents=True)
    (global_cfg / "config.json").write_text(json.dumps({
        "kb_roots": [{"name": "core", "path": "./knowledge"}]
    }))
    global_kb = global_project / "knowledge" / "shared"
    global_kb.mkdir(parents=True)
    (global_project / "knowledge" / "index.md").write_text(
        "---\nname: God Root\ndescription: Global KB root\n---\n\n# God KB"
    )
    (global_kb / "index.md").write_text(
        "---\nname: Shared Concepts\ndescription: Shared knowledge\n---\n\n# Shared\n\nGlobal content."
    )

    # Global reference config
    home_cfg = tmp_path / "home" / ".claude" / "knowledge-base"
    home_cfg.mkdir(parents=True)
    (home_cfg / "config.json").write_text(json.dumps({
        "namespace": "god",
        "source": str(global_project),
    }))

    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

    return tmp_path / "project", global_project


@pytest.fixture()
def global_kb_server(global_kb_project):
    """Server for a project with global KB."""
    project_path, _ = global_kb_project
    viewer_dir = str(
        Path(__file__).resolve().parent.parent.parent
        / "knowledge" / "view" / "skill" / "scripts"
    )
    server = create_server(0, str(project_path), viewer_dir)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


class TestGlobalKB:
    def _get(self, url):
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode())

    # --- Config ---

    def test_config_includes_global_entries(self, global_kb_server):
        data = self._get(f"{global_kb_server}/api/config")
        names = {e["name"] for e in data["kb_roots"]}
        assert "local" in names
        assert "god.core" in names

    def test_global_entries_marked_readonly(self, global_kb_server):
        data = self._get(f"{global_kb_server}/api/config")
        global_entries = [e for e in data["kb_roots"] if e.get("readonly")]
        assert len(global_entries) >= 1
        assert all(e["name"].startswith("god.") for e in global_entries)

    def test_local_entries_not_readonly(self, global_kb_server):
        data = self._get(f"{global_kb_server}/api/config")
        local_entries = [e for e in data["kb_roots"] if not e.get("readonly")]
        assert any(e["name"] == "local" for e in local_entries)

    # --- File serving ---

    def test_serve_global_file(self, global_kb_project, global_kb_server):
        _, global_project = global_kb_project
        abs_path = str(global_project / "knowledge" / "shared" / "index.md")
        data = self._get(f"{global_kb_server}/api/file?path={urllib.parse.quote(abs_path)}")
        assert data["meta"]["name"] == "Shared Concepts"
        assert "Global content" in data["body"]

    def test_global_file_marked_readonly(self, global_kb_project, global_kb_server):
        _, global_project = global_kb_project
        abs_path = str(global_project / "knowledge" / "shared" / "index.md")
        data = self._get(f"{global_kb_server}/api/file?path={urllib.parse.quote(abs_path)}")
        assert data.get("readonly") is True

    def test_local_file_not_marked_readonly(self, global_kb_server):
        data = self._get(f"{global_kb_server}/api/file?path=knowledge/topic/index.md")
        assert "readonly" not in data

    def test_random_absolute_path_rejected(self, global_kb_server):
        try:
            self._get(f"{global_kb_server}/api/file?path=/etc/passwd")
            assert False, "Should have raised"
        except urllib.error.HTTPError as e:
            assert e.code == 403

    # --- Search ---

    def test_search_includes_global_results(self, global_kb_server):
        data = self._get(f"{global_kb_server}/api/search?q=Shared")
        names = {r["name"] for r in data["results"]}
        assert "Shared Concepts" in names

    def test_search_global_results_tagged(self, global_kb_server):
        data = self._get(f"{global_kb_server}/api/search?q=Shared")
        global_hits = [r for r in data["results"] if r.get("global")]
        assert len(global_hits) >= 1

    def test_search_local_results_not_tagged_global(self, global_kb_server):
        data = self._get(f"{global_kb_server}/api/search?q=Local")
        local_hits = [r for r in data["results"] if r["name"] == "Local Topic"]
        assert len(local_hits) >= 1
        assert not any(r.get("global") for r in local_hits)

    def test_search_tiebreak_local_before_global(self, global_kb_project, global_kb_server):
        """When both local and global have the same score, local comes first."""
        _, global_project = global_kb_project
        # Add a note with same name to both KBs
        (Path(str(global_kb_project[0])) / "knowledge" / "topic" / "shared-note.md").write_text(
            "---\nname: Tiebreak Test\ndescription: Local version\n---\n\n# Local"
        )
        (global_project / "knowledge" / "shared" / "shared-note.md").write_text(
            "---\nname: Tiebreak Test\ndescription: Global version\n---\n\n# Global"
        )
        data = self._get(f"{global_kb_server}/api/search?q=Tiebreak+Test")
        ties = [r for r in data["results"] if r["name"] == "Tiebreak Test"]
        assert len(ties) >= 2
        # First result should be local (not global)
        assert not ties[0].get("global")
        assert ties[1].get("global")


# ===================================================================
# Integration tests: path deduplication (local == global path)
# ===================================================================

@pytest.fixture()
def same_path_project(tmp_path, monkeypatch):
    """Project where local KB path is the same as global KB path (self-referencing)."""
    # The project IS the god KB
    config_dir = tmp_path / "project" / ".claude" / "knowledge-base"
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text(json.dumps({
        "kb_roots": [{"name": "core", "path": "./knowledge"}]
    }))
    kb = tmp_path / "project" / "knowledge" / "topic"
    kb.mkdir(parents=True)
    (tmp_path / "project" / "knowledge" / "index.md").write_text(
        "---\nname: Root\ndescription: Root\n---\n\n# Root"
    )
    (kb / "index.md").write_text(
        "---\nname: Topic\ndescription: A topic\n---\n\n# Topic\n\nContent."
    )

    # Global config points to the SAME project as source
    home_cfg = tmp_path / "home" / ".claude" / "knowledge-base"
    home_cfg.mkdir(parents=True)
    (home_cfg / "config.json").write_text(json.dumps({
        "namespace": "god",
        "source": str(tmp_path / "project"),
    }))

    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    return tmp_path / "project"


@pytest.fixture()
def same_path_server(same_path_project):
    viewer_dir = str(
        Path(__file__).resolve().parent.parent.parent
        / "knowledge" / "view" / "skill" / "scripts"
    )
    server = create_server(0, str(same_path_project), viewer_dir)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


class TestPathDeduplication:
    def _get(self, url):
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode())

    def test_config_deduplicates_same_path(self, same_path_server):
        """When local and global resolve to same path, global entry is dropped."""
        data = self._get(f"{same_path_server}/api/config")
        names = [e["name"] for e in data["kb_roots"]]
        assert "core" in names
        assert "god.core" not in names

    def test_search_no_duplicates(self, same_path_server):
        """Search should not return the same file twice."""
        data = self._get(f"{same_path_server}/api/search?q=Topic")
        topic_hits = [r for r in data["results"] if r["name"] == "Topic"]
        assert len(topic_hits) == 1

    def test_deduplicated_results_not_tagged_global(self, same_path_server):
        """When deduped, the remaining entry should be local (not global)."""
        data = self._get(f"{same_path_server}/api/search?q=Topic")
        topic_hits = [r for r in data["results"] if r["name"] == "Topic"]
        assert len(topic_hits) >= 1
        assert not topic_hits[0].get("global")


# ===================================================================
# kb_loader: merge_configs path deduplication
# ===================================================================

class TestMergeConfigsPathDedup:
    def test_same_resolved_path_skipped(self, tmp_path):
        from kb_loader import KBConfig, KBEntry, merge_configs
        # Create a real directory so Path.resolve() works
        kb_dir = tmp_path / "knowledge"
        kb_dir.mkdir()
        project = KBConfig(entries=[KBEntry("core", str(kb_dir))])
        global_ = KBConfig(entries=[KBEntry("god.core", str(kb_dir), readonly=True)])
        merged = merge_configs(project, global_)
        assert len(merged.entries) == 1
        assert merged.entries[0].name == "core"

    def test_different_paths_both_kept(self, tmp_path):
        from kb_loader import KBConfig, KBEntry, merge_configs
        local_dir = tmp_path / "local"
        global_dir = tmp_path / "global"
        local_dir.mkdir()
        global_dir.mkdir()
        project = KBConfig(entries=[KBEntry("core", str(local_dir))])
        global_ = KBConfig(entries=[KBEntry("god.core", str(global_dir), readonly=True)])
        merged = merge_configs(project, global_)
        assert len(merged.entries) == 2

    def test_dotslash_vs_absolute_deduped(self, tmp_path, monkeypatch):
        """./knowledge and /absolute/path/knowledge resolve to same dir."""
        from kb_loader import KBConfig, KBEntry, merge_configs
        kb_dir = tmp_path / "knowledge"
        kb_dir.mkdir()
        monkeypatch.chdir(tmp_path)
        project = KBConfig(entries=[KBEntry("core", "./knowledge")])
        global_ = KBConfig(entries=[KBEntry("god.core", str(kb_dir), readonly=True)])
        merged = merge_configs(project, global_)
        assert len(merged.entries) == 1
        assert merged.entries[0].name == "core"


# ===================================================================
# Tests: global KBs grouped under "global" super folder in sidebar
# ===================================================================

class TestGlobalKBSidebarGrouping:
    """Sidebar must group global KBs under a collapsible 'global' super folder."""

    def _get_html(self, url):
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.read().decode()

    def test_html_has_render_tree_with_local_global_split(self, server_url):
        """renderTree separates KBs into localKBs and globalKBs."""
        html = self._get_html(f"{server_url}/")
        assert "localKBs" in html
        assert "globalKBs" in html
        assert "treeData.kbs.filter(kb => !kb.readonly)" in html
        assert "treeData.kbs.filter(kb => kb.readonly)" in html

    def test_html_has_global_super_folder_label(self, server_url):
        """A 'global' super folder label with the tree-kb-label-global class exists."""
        html = self._get_html(f"{server_url}/")
        assert "tree-kb-label-global" in html
        # The label text is "global"
        assert '"global \\u25B8"' in html or "global \\u25B8" in html or 'global \u25B8' in html

    def test_global_super_folder_collapsed_by_default(self, server_url):
        """Global wrapper has class 'tree-children' without 'open' (collapsed)."""
        html = self._get_html(f"{server_url}/")
        # The global wrapper: className = "tree-children" (no "open")
        assert 'globalWrap.className = "tree-children"' in html
        # Verify the comment explains the intent
        assert "collapsed by default" in html

    def test_global_super_folder_toggle_logic(self, server_url):
        """Clicking the global label toggles open/collapsed state."""
        html = self._get_html(f"{server_url}/")
        assert "globalWrap.classList.toggle" in html

    def test_render_kb_section_extracted(self, server_url):
        """renderKBSection is a standalone function used for both local and global KBs."""
        html = self._get_html(f"{server_url}/")
        assert "function renderKBSection(container, kb)" in html
        # Both local and global loops call it
        assert "renderKBSection(container, kb)" in html
        assert "renderKBSection(globalWrap, kb)" in html

    def test_global_super_folder_css_exists(self, server_url):
        """CSS for .tree-kb-label-global includes border-top separator."""
        html = self._get_html(f"{server_url}/")
        assert ".tree-kb-label-global" in html
        assert "border-top" in html

    def test_local_kbs_rendered_before_global(self, server_url):
        """Local KBs are rendered first, global grouped after."""
        html = self._get_html(f"{server_url}/")
        local_pos = html.index("for (const kb of localKBs)")
        global_pos = html.index("if (globalKBs.length > 0)")
        assert local_pos < global_pos


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
