"""Tests for suggestion.py — file-based suggestion pipeline for global KBs."""

from pathlib import Path
from unittest import mock

import pytest
from suggestion import (
    create_suggestion,
    format_suggestion,
    list_suggestions,
    _parse_frontmatter,
    _strip_frontmatter,
    _slugify,
)


class TestSlugify:
    def test_basic(self):
        assert _slugify("concurrency/actors") == "concurrency-actors"

    def test_special_chars(self):
        assert _slugify("Hello World! @#$") == "hello-world"

    def test_truncation(self):
        long = "a" * 100
        assert len(_slugify(long)) <= 60


class TestParseFrontmatter:
    def test_basic(self):
        text = '---\ntarget_kb: god.core\naction: create\n---\nBody'
        meta = _parse_frontmatter(text)
        assert meta["target_kb"] == "god.core"
        assert meta["action"] == "create"

    def test_no_frontmatter(self):
        assert _parse_frontmatter("Just content") == {}

    def test_quoted_values(self):
        text = '---\nreason: "A good reason"\n---\n'
        meta = _parse_frontmatter(text)
        assert meta["reason"] == "A good reason"


class TestStripFrontmatter:
    def test_strips(self):
        text = "---\nkey: val\n---\nBody here"
        assert _strip_frontmatter(text) == "Body here"

    def test_no_frontmatter(self):
        text = "Just content"
        assert _strip_frontmatter(text) == text


class TestCreateSuggestion:
    def test_creates_file(self, tmp_path):
        with mock.patch("suggestion._suggestions_dir", return_value=tmp_path):
            path = create_suggestion(
                target_kb="god.core",
                target_path="~/knowledge/core",
                topic="concurrency/actors",
                action="create",
                reason="Found useful pattern",
                content="# Actors\n\nContent about actors.",
                source_project="/dev/my-project",
            )
        assert path.exists()
        text = path.read_text()
        assert "target_kb: god.core" in text
        assert "target_path: ~/knowledge/core" in text
        assert "topic: concurrency/actors" in text
        assert "action: create" in text
        assert "status: pending" in text
        assert "# Actors" in text

    def test_creates_directory(self, tmp_path):
        sub = tmp_path / "new" / "dir"
        with mock.patch("suggestion._suggestions_dir", return_value=sub):
            path = create_suggestion(
                target_kb="god.core",
                target_path="~/knowledge/core",
                topic="topic",
                action="update",
                reason="test",
                content="content",
            )
        assert sub.exists()
        assert path.exists()

    def test_filename_format(self, tmp_path):
        with mock.patch("suggestion._suggestions_dir", return_value=tmp_path):
            path = create_suggestion(
                target_kb="god.core",
                target_path="~/knowledge/core",
                topic="concurrency/actors",
                action="create",
                reason="test",
                content="content",
            )
        # Filename: <timestamp>-<slug>.md
        assert path.name.endswith("-concurrency-actors.md")
        assert path.suffix == ".md"


class TestListSuggestions:
    def test_lists_files(self, tmp_path):
        # Create two suggestion files
        (tmp_path / "20260323-a.md").write_text(
            "---\ntarget_kb: god.core\nstatus: pending\ntopic: a\n---\nContent A"
        )
        (tmp_path / "20260323-b.md").write_text(
            "---\ntarget_kb: god.swift\nstatus: applied\ntopic: b\n---\nContent B"
        )
        with mock.patch("suggestion._suggestions_dir", return_value=tmp_path):
            items = list_suggestions()
        assert len(items) == 2

    def test_filter_by_status(self, tmp_path):
        (tmp_path / "a.md").write_text("---\nstatus: pending\n---\n")
        (tmp_path / "b.md").write_text("---\nstatus: applied\n---\n")
        with mock.patch("suggestion._suggestions_dir", return_value=tmp_path):
            pending = list_suggestions(status_filter="pending")
            applied = list_suggestions(status_filter="applied")
        assert len(pending) == 1
        assert len(applied) == 1

    def test_empty_dir(self, tmp_path):
        with mock.patch("suggestion._suggestions_dir", return_value=tmp_path):
            assert list_suggestions() == []

    def test_missing_dir(self, tmp_path):
        missing = tmp_path / "nonexistent"
        with mock.patch("suggestion._suggestions_dir", return_value=missing):
            assert list_suggestions() == []


class TestFormatSuggestion:
    def test_format(self, tmp_path):
        f = tmp_path / "suggestion.md"
        f.write_text(
            "---\n"
            "target_kb: god.core\n"
            "target_path: ~/knowledge/core\n"
            "topic: concurrency/actors\n"
            "action: create\n"
            'reason: "Found pattern"\n'
            "source_project: /dev/proj\n"
            "created: 2026-03-23T14:00:00\n"
            "status: pending\n"
            "---\n\n"
            "# Actors\n\nContent here.\n"
        )
        text = format_suggestion(str(f))
        assert "god.core" in text
        assert "concurrency/actors" in text
        assert "# Actors" in text
