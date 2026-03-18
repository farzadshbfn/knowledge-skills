"""Tests for link extraction, normalization, broken links, and wikilinks."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validate_kb import check_broken_links, check_wikilinks, extract_md_links, normalize_path


class TestExtractMdLinks:
    def test_basic_link(self):
        assert extract_md_links("See [note](other.md) for details.") == [(1, "other.md")]

    def test_multiple_links_one_line(self):
        assert extract_md_links("[a](a.md) and [b](b.md)") == [(1, "a.md"), (1, "b.md")]

    def test_relative_path_link(self):
        assert extract_md_links("[note](../topic/note.md)") == [(1, "../topic/note.md")]

    def test_ignores_non_md_links(self):
        assert extract_md_links("[site](https://example.com)") == []

    def test_ignores_fenced_code_block(self):
        content = "Before\n```\n[link](fake.md)\n```\nAfter [real](real.md)\n"
        assert extract_md_links(content) == [(5, "real.md")]

    def test_ignores_inline_code(self):
        content = "Text `[link](fake.md)` and [real](real.md)\n"
        assert extract_md_links(content) == [(1, "real.md")]

    def test_empty_content(self):
        assert extract_md_links("") == []

    def test_link_on_multiple_lines(self):
        content = "Line 1\nLine 2 [a](a.md)\nLine 3\nLine 4 [b](b.md)\n"
        assert extract_md_links(content) == [(2, "a.md"), (4, "b.md")]

    def test_backtick_wrapped_link_text(self):
        content = "See [`skill/SKILL.md`](skill/SKILL.md) for details."
        assert extract_md_links(content) == [(1, "skill/SKILL.md")]


class TestNormalizePath:
    def test_simple_relative(self):
        assert normalize_path("topic", "note.md") == "topic/note.md"

    def test_parent_traversal(self):
        assert normalize_path("topic", "../other/note.md") == "other/note.md"

    def test_double_parent(self):
        assert normalize_path("a/b", "../../c/d.md") == "c/d.md"

    def test_dot_current(self):
        assert normalize_path("topic", "./note.md") == "topic/note.md"

    def test_absolute_link(self):
        assert normalize_path("topic", "/other.md") == "other.md"

    def test_empty_base(self):
        assert normalize_path("", "note.md") == "note.md"


class TestCheckBrokenLinks:
    def test_no_broken_links(self):
        files = {"a/index.md": "See [note](note.md).", "a/note.md": "Content."}
        assert check_broken_links(files) == []

    def test_broken_internal_link(self):
        files = {"a/index.md": "See [missing](nonexistent.md)."}
        issues = check_broken_links(files)
        assert len(issues) == 1
        assert issues[0].check == "broken_link"

    def test_cross_directory_link(self):
        files = {"a/note.md": "See [b](../b/note.md).", "b/note.md": "Content."}
        assert check_broken_links(files) == []

    def test_broken_cross_directory_link(self):
        files = {"a/note.md": "See [b](../b/missing.md).", "b/note.md": "Content."}
        assert len(check_broken_links(files)) == 1

    def test_check_scope_limits_checked_files(self):
        files = {"a/index.md": "See [missing](gone.md).", "a/note.md": "See [also-missing](gone2.md)."}
        issues = check_broken_links(files, check_scope={"a/index.md"})
        assert len(issues) == 1
        assert issues[0].file == "a/index.md"

    def test_links_in_code_blocks_ignored(self):
        files = {"a/note.md": "```\n[fake](fake.md)\n```\n"}
        assert check_broken_links(files) == []

    def test_at_links_not_flagged_as_broken(self):
        files = {"topic/note.md": "See [@ios/other.md](@ios/other.md)."}
        assert not any(i.check == "broken_link" for i in check_broken_links(files))


class TestCheckWikilinks:
    def test_no_wikilinks(self):
        files = {"a/note.md": "Normal [link](other.md)."}
        assert check_wikilinks(files) == []

    def test_wikilink_detected(self):
        files = {"a/note.md": "See [[some-page]] here."}
        issues = check_wikilinks(files)
        assert len(issues) == 1
        assert issues[0].check == "wikilink"

    def test_wikilink_in_code_block_ignored(self):
        assert check_wikilinks({"a/note.md": "```\n[[fake]]\n```\n"}) == []

    def test_wikilink_in_inline_code_ignored(self):
        assert check_wikilinks({"a/note.md": "Use `[[this]]` syntax."}) == []

    def test_check_scope(self):
        files = {"a/note.md": "[[wiki1]]", "b/note.md": "[[wiki2]]"}
        issues = check_wikilinks(files, check_scope={"a/note.md"})
        assert len(issues) == 1
        assert issues[0].file == "a/note.md"
