"""Tests for analyze_access.py — KB access log analysis CLI."""

import json
import os
import sys

import pytest
from analyze_access import (
    AnalysisResult,
    HealthEntry,
    TopicStats,
    analyze,
    compute_topic_stats,
    find_candidates,
    format_context,
    format_json,
    is_global_kb_source,
    load_global_log,
    load_health,
    load_log,
    main,
)
from monitor_helpers import (
    MEMORY_EMPTY,
    MEMORY_WITH_GATES,
    make_global_log_entry,
    make_log_entry,
    setup_access_log,
    setup_global_access_log,
    setup_global_config,
    setup_kb_config,
    setup_memory_dir,
    setup_topic_with_skill,
    setup_topic_without_skill,
)

# ===================================================================
# load_log
# ===================================================================

class TestLoadLog:
    def test_empty_log(self, tmp_path):
        setup_access_log(tmp_path, [])
        entries = load_log(str(tmp_path))
        assert entries == []

    def test_valid_entries(self, tmp_path):
        setup_access_log(tmp_path, [
            make_log_entry("topic-a"),
            make_log_entry("topic-b"),
        ])
        entries = load_log(str(tmp_path))
        assert len(entries) == 2
        assert entries[0]["topic"] == "topic-a"

    def test_malformed_entries_skipped(self, tmp_path):
        log_dir = tmp_path / ".claude" / "knowledge-base"
        log_dir.mkdir(parents=True)
        log_file = log_dir / "access-log.jsonl"
        log_file.write_text(
            json.dumps(make_log_entry("good")) + "\n"
            + "not valid json\n"
            + json.dumps(make_log_entry("also-good")) + "\n"
        )
        entries = load_log(str(tmp_path))
        assert len(entries) == 2

    def test_missing_file(self, tmp_path):
        entries = load_log(str(tmp_path))
        assert entries == []

# ===================================================================
# is_global_kb_source
# ===================================================================

class TestIsGlobalKBSource:
    def test_matching_source(self, tmp_path, monkeypatch):
        source_dir = tmp_path / "source-project"
        source_dir.mkdir()
        home_dir = tmp_path / "home"
        setup_global_config(home_dir, str(source_dir))
        monkeypatch.setattr("os.path.expanduser",
                            lambda p: p.replace("~", str(home_dir)))
        assert is_global_kb_source(str(source_dir)) is True

    def test_different_project(self, tmp_path, monkeypatch):
        source_dir = tmp_path / "source-project"
        source_dir.mkdir()
        other_dir = tmp_path / "other-project"
        other_dir.mkdir()
        home_dir = tmp_path / "home"
        setup_global_config(home_dir, str(source_dir))
        monkeypatch.setattr("os.path.expanduser",
                            lambda p: p.replace("~", str(home_dir)))
        assert is_global_kb_source(str(other_dir)) is False

    def test_missing_global_config(self, tmp_path, monkeypatch):
        home_dir = tmp_path / "empty-home"
        home_dir.mkdir()
        monkeypatch.setattr("os.path.expanduser",
                            lambda p: p.replace("~", str(home_dir)))
        assert is_global_kb_source(str(tmp_path)) is False

# ===================================================================
# load_global_log
# ===================================================================

class TestLoadGlobalLog:
    def test_loads_entries(self, tmp_path, monkeypatch):
        home_dir = tmp_path / "home"
        setup_global_access_log(home_dir, [
            make_global_log_entry("topic-a", source_project="proj1"),
            make_global_log_entry("topic-b", source_project="proj2"),
        ])
        monkeypatch.setattr(
            "analyze_access.GLOBAL_LOG_FILE",
            str(home_dir / ".claude" / "knowledge-base" / "access-log.jsonl"),
        )
        entries = load_global_log()
        assert len(entries) == 2
        assert entries[0]["source_project"] == "proj1"

    def test_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "analyze_access.GLOBAL_LOG_FILE",
            str(tmp_path / "nonexistent.jsonl"),
        )
        assert load_global_log() == []

# ===================================================================
# compute_topic_stats
# ===================================================================

class TestComputeTopicStats:
    def test_single_topic_single_session(self, tmp_path):
        setup_kb_config(tmp_path)
        entries = [make_log_entry("my-topic", sid="sess1")]
        stats = compute_topic_stats(entries, str(tmp_path))
        assert len(stats) == 1
        assert stats[0].topic == "my-topic"
        assert stats[0].sessions == 1
        assert stats[0].reads == 1

    def test_single_topic_multiple_sessions(self, tmp_path):
        setup_kb_config(tmp_path)
        entries = [
            make_log_entry("my-topic", sid="sess1"),
            make_log_entry("my-topic", sid="sess1"),
            make_log_entry("my-topic", sid="sess2"),
            make_log_entry("my-topic", sid="sess3"),
        ]
        stats = compute_topic_stats(entries, str(tmp_path))
        assert len(stats) == 1
        assert stats[0].sessions == 3
        assert stats[0].reads == 4

    def test_multiple_topics_sorted_by_sessions(self, tmp_path):
        setup_kb_config(tmp_path)
        entries = [
            make_log_entry("low", sid="s1"),
            make_log_entry("high", sid="s1"),
            make_log_entry("high", sid="s2"),
            make_log_entry("high", sid="s3"),
        ]
        stats = compute_topic_stats(entries, str(tmp_path))
        assert stats[0].topic == "high"
        assert stats[0].sessions == 3
        assert stats[1].topic == "low"
        assert stats[1].sessions == 1

    def test_has_skill_detection(self, tmp_path):
        setup_kb_config(tmp_path)
        setup_topic_with_skill(tmp_path, "skilled")
        setup_topic_without_skill(tmp_path, "unskilled")
        entries = [
            make_log_entry("skilled"),
            make_log_entry("unskilled"),
        ]
        stats = compute_topic_stats(entries, str(tmp_path))
        by_topic = {s.topic: s for s in stats}
        assert by_topic["skilled"].has_skill is True
        assert by_topic["unskilled"].has_skill is False

    def test_last_read_tracked(self, tmp_path):
        setup_kb_config(tmp_path)
        entries = [
            make_log_entry("my-topic", ts="2026-03-10T10:00:00"),
            make_log_entry("my-topic", ts="2026-03-14T15:30:00"),
            make_log_entry("my-topic", ts="2026-03-12T08:00:00"),
        ]
        stats = compute_topic_stats(entries, str(tmp_path))
        assert stats[0].last_read == "2026-03-14T15:30:00"

    def test_empty_entries(self, tmp_path):
        setup_kb_config(tmp_path)
        stats = compute_topic_stats([], str(tmp_path))
        assert stats == []

    def test_source_projects_counted(self, tmp_path):
        setup_kb_config(tmp_path)
        entries = [
            make_global_log_entry("topic-a", sid="s1", source_project="proj1"),
            make_global_log_entry("topic-a", sid="s2", source_project="proj2"),
            make_global_log_entry("topic-a", sid="s3", source_project="proj1"),
        ]
        stats = compute_topic_stats(entries, str(tmp_path))
        assert stats[0].source_projects == 2

    def test_no_source_project_field_zero(self, tmp_path):
        setup_kb_config(tmp_path)
        entries = [make_log_entry("topic-a", sid="s1")]
        stats = compute_topic_stats(entries, str(tmp_path))
        assert stats[0].source_projects == 0

# ===================================================================
# find_candidates
# ===================================================================

class TestFindCandidates:
    def _make_stats(self, topic, sessions, reads, has_skill=False):
        return TopicStats(
            topic=topic, sessions=sessions, reads=reads, has_skill=has_skill
        )

    def test_meets_both_thresholds(self, tmp_path, monkeypatch):
        monkeypatch.setattr("analyze_access._is_gated", lambda t, c: False)
        stats = [self._make_stats("hot-topic", sessions=6, reads=20)]
        candidates = find_candidates(stats, str(tmp_path))
        assert len(candidates) == 1
        assert candidates[0].topic == "hot-topic"

    def test_below_session_threshold(self, tmp_path, monkeypatch):
        monkeypatch.setattr("analyze_access._is_gated", lambda t, c: False)
        stats = [self._make_stats("few-sessions", sessions=2, reads=20)]
        candidates = find_candidates(stats, str(tmp_path))
        assert candidates == []

    def test_below_read_threshold(self, tmp_path, monkeypatch):
        monkeypatch.setattr("analyze_access._is_gated", lambda t, c: False)
        stats = [self._make_stats("few-reads", sessions=6, reads=8)]
        candidates = find_candidates(stats, str(tmp_path))
        assert candidates == []

    def test_has_skill_excluded(self, tmp_path, monkeypatch):
        monkeypatch.setattr("analyze_access._is_gated", lambda t, c: False)
        stats = [self._make_stats("skilled", sessions=10, reads=50, has_skill=True)]
        candidates = find_candidates(stats, str(tmp_path))
        assert candidates == []

    def test_gated_topic_excluded(self, tmp_path, monkeypatch):
        monkeypatch.setattr("analyze_access._is_gated", lambda t, c: True)
        stats = [self._make_stats("gated", sessions=10, reads=50)]
        candidates = find_candidates(stats, str(tmp_path))
        assert candidates == []

    def test_exact_thresholds_pass(self, tmp_path, monkeypatch):
        """Exactly at threshold values (3 sessions, 9 reads) should pass."""
        monkeypatch.setattr("analyze_access._is_gated", lambda t, c: False)
        stats = [self._make_stats("borderline", sessions=3, reads=9)]
        candidates = find_candidates(stats, str(tmp_path))
        assert len(candidates) == 1

    def test_just_below_thresholds_fail(self, tmp_path, monkeypatch):
        monkeypatch.setattr("analyze_access._is_gated", lambda t, c: False)
        stats = [self._make_stats("almost", sessions=2, reads=9)]
        assert find_candidates(stats, str(tmp_path)) == []
        stats = [self._make_stats("almost", sessions=3, reads=8)]
        assert find_candidates(stats, str(tmp_path)) == []

    def test_mixed_candidates_and_non(self, tmp_path, monkeypatch):
        monkeypatch.setattr("analyze_access._is_gated", lambda t, c: False)
        stats = [
            self._make_stats("yes", sessions=8, reads=30),
            self._make_stats("no-sessions", sessions=1, reads=30),
            self._make_stats("no-reads", sessions=8, reads=5),
            self._make_stats("has-skill", sessions=8, reads=30, has_skill=True),
            self._make_stats("also-yes", sessions=3, reads=9),
        ]
        candidates = find_candidates(stats, str(tmp_path))
        topics = {c.topic for c in candidates}
        assert topics == {"yes", "also-yes"}

    def test_custom_thresholds(self, tmp_path, monkeypatch):
        monkeypatch.setattr("analyze_access._is_gated", lambda t, c: False)
        stats = [self._make_stats("low-bar", sessions=2, reads=5)]
        candidates = find_candidates(stats, str(tmp_path), min_sessions=2, min_reads=5)
        assert len(candidates) == 1

# ===================================================================
# load_health
# ===================================================================

class TestLoadHealth:
    def test_valid_health_entries(self, tmp_path, monkeypatch):
        mem_dir = setup_memory_dir(tmp_path, MEMORY_WITH_GATES)
        monkeypatch.setattr("analyze_access._find_memory_dir", lambda cwd: str(mem_dir))
        entries = load_health(str(tmp_path))
        assert len(entries) == 2
        assert entries[0].skill == "/writing-article"
        assert entries[0].corrections == 3
        assert entries[0].status == "action"
        assert entries[1].skill == "/kb-find"
        assert entries[1].corrections == 1
        assert entries[1].status == "watch"

    def test_empty_health_section(self, tmp_path, monkeypatch):
        mem_dir = setup_memory_dir(tmp_path, MEMORY_EMPTY)
        monkeypatch.setattr("analyze_access._find_memory_dir", lambda cwd: str(mem_dir))
        entries = load_health(str(tmp_path))
        assert entries == []

    def test_missing_memory_file(self, tmp_path, monkeypatch):
        mem_dir = setup_memory_dir(tmp_path)  # no file
        monkeypatch.setattr("analyze_access._find_memory_dir", lambda cwd: str(mem_dir))
        entries = load_health(str(tmp_path))
        assert entries == []

    def test_no_memory_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("analyze_access._find_memory_dir", lambda cwd: None)
        entries = load_health(str(tmp_path))
        assert entries == []

# ===================================================================
# format_json
# ===================================================================

class TestFormatJson:
    def test_with_top_topics(self):
        result = AnalysisResult(
            top_topics=[TopicStats("my-topic", sessions=5, reads=20, has_skill=False)]
        )
        parsed = json.loads(format_json(result))
        assert len(parsed["top_topics"]) == 1
        assert parsed["top_topics"][0]["topic"] == "my-topic"
        assert parsed["top_topics"][0]["sessions"] == 5

    def test_with_candidates(self):
        result = AnalysisResult(
            candidates=[TopicStats("cand", sessions=6, reads=25)]
        )
        parsed = json.loads(format_json(result))
        assert len(parsed["candidates"]) == 1
        assert "has_skill" not in parsed["candidates"][0]  # not included in candidates

    def test_with_health(self):
        result = AnalysisResult(
            health=[HealthEntry("writing", corrections=3, last_issue="tone", status="action")]
        )
        parsed = json.loads(format_json(result))
        assert parsed["health"][0]["corrections"] == 3

    def test_source_projects_in_top_topics(self):
        result = AnalysisResult(
            top_topics=[TopicStats("t", sessions=5, reads=20, source_projects=3)]
        )
        parsed = json.loads(format_json(result))
        assert parsed["top_topics"][0]["source_projects"] == 3

    def test_source_projects_omitted_when_zero(self):
        result = AnalysisResult(
            top_topics=[TopicStats("t", sessions=5, reads=20, source_projects=0)]
        )
        parsed = json.loads(format_json(result))
        assert "source_projects" not in parsed["top_topics"][0]

    def test_empty_result(self):
        result = AnalysisResult()
        parsed = json.loads(format_json(result))
        assert parsed == {}

    def test_all_fields(self):
        result = AnalysisResult(
            top_topics=[TopicStats("t", 1, 1)],
            candidates=[TopicStats("c", 5, 15)],
            health=[HealthEntry("s", 2, "issue", "watch")],
        )
        parsed = json.loads(format_json(result))
        assert "top_topics" in parsed
        assert "candidates" in parsed
        assert "health" in parsed

# ===================================================================
# format_context
# ===================================================================

class TestFormatContext:
    def test_with_single_candidate(self):
        result = AnalysisResult(
            candidates=[TopicStats("claude-mcp", sessions=8, reads=23)]
        )
        ctx = format_context(result)
        assert "[kb-monitor]" in ctx
        assert "claude-mcp/" in ctx
        assert "8 sessions" in ctx
        assert "23 reads" in ctx
        assert "/kb-monitor" in ctx

    def test_with_multiple_candidates(self):
        result = AnalysisResult(
            candidates=[
                TopicStats("topic-a", sessions=8, reads=23),
                TopicStats("topic-b", sessions=6, reads=18),
            ]
        )
        ctx = format_context(result)
        assert "2 skill candidates" in ctx
        assert "+1 more" in ctx

    def test_with_health_issues(self):
        result = AnalysisResult(
            health=[HealthEntry("writing-article", 3, "tone issue", "action")]
        )
        ctx = format_context(result)
        assert "1 health issue" in ctx
        assert "/writing-article" in ctx
        assert "action status" in ctx

    def test_with_watch_status_included(self):
        result = AnalysisResult(
            health=[HealthEntry("skill-a", 1, "minor", "watch")]
        )
        ctx = format_context(result)
        assert "watch status" in ctx

    def test_ok_status_excluded(self):
        result = AnalysisResult(
            health=[HealthEntry("healthy-skill", 0, "", "ok")]
        )
        ctx = format_context(result)
        assert ctx == ""

    def test_both_candidates_and_health(self):
        result = AnalysisResult(
            candidates=[TopicStats("topic-a", 8, 23)],
            health=[HealthEntry("writing", 3, "tone", "action")],
        )
        ctx = format_context(result)
        assert "skill candidate" in ctx
        assert "health issue" in ctx

    def test_empty_result(self):
        result = AnalysisResult()
        assert format_context(result) == ""

    def test_no_candidates_no_health_issues(self):
        result = AnalysisResult(
            candidates=[],
            health=[HealthEntry("ok-skill", 0, "", "ok")],
        )
        assert format_context(result) == ""

    def test_cross_project_info_shown(self):
        result = AnalysisResult(
            candidates=[TopicStats("topic-a", sessions=8, reads=23, source_projects=3)]
        )
        ctx = format_context(result)
        assert "3 projects" in ctx

    def test_single_project_no_project_info(self):
        result = AnalysisResult(
            candidates=[TopicStats("topic-a", sessions=8, reads=23, source_projects=1)]
        )
        ctx = format_context(result)
        assert "project" not in ctx

# ===================================================================
# analyze (integration)
# ===================================================================

class TestAnalyze:
    def test_full_analysis(self, tmp_path, monkeypatch):
        setup_kb_config(tmp_path)
        setup_topic_without_skill(tmp_path, "hot-topic")
        # 6 unique sessions, 20 total reads
        entries = []
        for i in range(6):
            for _ in range(3 if i < 4 else 4):
                entries.append(make_log_entry("hot-topic", sid=f"sess{i:04d}"))
        setup_access_log(tmp_path, entries)
        mem_dir = setup_memory_dir(tmp_path, MEMORY_WITH_GATES)
        monkeypatch.setattr("analyze_access._find_memory_dir", lambda cwd: str(mem_dir))

        result = analyze(
            str(tmp_path), include_top=True, include_candidates=True, include_health=True
        )
        assert len(result.top_topics) >= 1
        assert result.top_topics[0].topic == "hot-topic"
        assert len(result.candidates) >= 1
        assert len(result.health) == 2

    def test_no_log_no_crash(self, tmp_path, monkeypatch):
        monkeypatch.setattr("analyze_access._find_memory_dir", lambda cwd: None)
        result = analyze(str(tmp_path), include_top=True, include_candidates=True)
        assert result.top_topics == []
        assert result.candidates == []

    def test_selective_includes(self, tmp_path, monkeypatch):
        setup_kb_config(tmp_path)
        setup_access_log(tmp_path, [make_log_entry("t")])
        monkeypatch.setattr("analyze_access._find_memory_dir", lambda cwd: None)

        result = analyze(str(tmp_path), include_top=True)
        assert len(result.top_topics) == 1
        assert result.candidates == []
        assert result.health == []

# ===================================================================
# analyze with global log
# ===================================================================

class TestAnalyzeWithGlobal:
    def test_auto_detects_global_source(self, tmp_path, monkeypatch):
        """When cwd is the global KB source, shared log is auto-included."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        setup_kb_config(source_dir)
        setup_access_log(source_dir, [make_log_entry("local-topic", sid="s1")])

        home_dir = tmp_path / "home"
        setup_global_config(home_dir, str(source_dir))
        setup_global_access_log(home_dir, [
            make_global_log_entry("global-topic", sid="s2", source_project="proj-a"),
        ])
        monkeypatch.setattr("os.path.expanduser",
                            lambda p: p.replace("~", str(home_dir)))
        monkeypatch.setattr(
            "analyze_access.GLOBAL_LOG_FILE",
            str(home_dir / ".claude" / "knowledge-base" / "access-log.jsonl"),
        )
        monkeypatch.setattr("analyze_access._find_memory_dir", lambda cwd: None)

        result = analyze(str(source_dir), include_top=True)
        topics = {s.topic for s in result.top_topics}
        assert "local-topic" in topics
        assert "global-topic" in topics

    def test_non_source_excludes_global(self, tmp_path, monkeypatch):
        """Projects that aren't the global source don't auto-include shared log."""
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        setup_kb_config(other_dir)
        setup_access_log(other_dir, [make_log_entry("local-only", sid="s1")])

        source_dir = tmp_path / "source"
        source_dir.mkdir()
        home_dir = tmp_path / "home"
        setup_global_config(home_dir, str(source_dir))
        setup_global_access_log(home_dir, [
            make_global_log_entry("should-not-appear", sid="s2"),
        ])
        monkeypatch.setattr("os.path.expanduser",
                            lambda p: p.replace("~", str(home_dir)))
        monkeypatch.setattr(
            "analyze_access.GLOBAL_LOG_FILE",
            str(home_dir / ".claude" / "knowledge-base" / "access-log.jsonl"),
        )
        monkeypatch.setattr("analyze_access._find_memory_dir", lambda cwd: None)

        result = analyze(str(other_dir), include_top=True)
        topics = {s.topic for s in result.top_topics}
        assert "local-only" in topics
        assert "should-not-appear" not in topics

    def test_explicit_include_global_flag(self, tmp_path, monkeypatch):
        """Explicit include_global=True forces shared log inclusion."""
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        setup_kb_config(other_dir)
        setup_access_log(other_dir, [])

        home_dir = tmp_path / "home"
        setup_global_access_log(home_dir, [
            make_global_log_entry("forced-global", sid="s1"),
        ])
        monkeypatch.setattr("os.path.expanduser",
                            lambda p: p.replace("~", str(home_dir)))
        monkeypatch.setattr(
            "analyze_access.GLOBAL_LOG_FILE",
            str(home_dir / ".claude" / "knowledge-base" / "access-log.jsonl"),
        )
        monkeypatch.setattr("analyze_access._find_memory_dir", lambda cwd: None)

        result = analyze(str(other_dir), include_top=True, include_global=True)
        topics = {s.topic for s in result.top_topics}
        assert "forced-global" in topics

# ===================================================================
# main (CLI)
# ===================================================================

class TestMain:
    def test_top_topics_json(self, tmp_path, monkeypatch, capsys):
        setup_kb_config(tmp_path)
        setup_access_log(tmp_path, [make_log_entry("my-topic")])
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        monkeypatch.setattr("analyze_access._find_memory_dir", lambda cwd: None)

        result = main(["--top-topics"])
        assert result == 0
        parsed = json.loads(capsys.readouterr().out)
        assert "top_topics" in parsed

    def test_candidates_json(self, tmp_path, monkeypatch, capsys):
        setup_kb_config(tmp_path)
        setup_topic_without_skill(tmp_path, "hot")
        entries = []
        for i in range(5):
            for _ in range(3):
                entries.append(make_log_entry("hot", sid=f"s{i:04d}"))
        setup_access_log(tmp_path, entries)
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        monkeypatch.setattr("analyze_access._is_gated", lambda t, c: False)

        result = main(["--candidates"])
        assert result == 0
        parsed = json.loads(capsys.readouterr().out)
        assert len(parsed["candidates"]) == 1

    def test_health_json(self, tmp_path, monkeypatch, capsys):
        setup_kb_config(tmp_path)
        setup_access_log(tmp_path, [])
        mem_dir = setup_memory_dir(tmp_path, MEMORY_WITH_GATES)
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        monkeypatch.setattr("analyze_access._find_memory_dir", lambda cwd: str(mem_dir))

        result = main(["--health"])
        assert result == 0
        parsed = json.loads(capsys.readouterr().out)
        assert len(parsed["health"]) == 2

    def test_context_format(self, tmp_path, monkeypatch, capsys):
        setup_kb_config(tmp_path)
        setup_topic_without_skill(tmp_path, "hot")
        entries = []
        for i in range(5):
            for _ in range(3):
                entries.append(make_log_entry("hot", sid=f"s{i:04d}"))
        setup_access_log(tmp_path, entries)
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        monkeypatch.setattr("analyze_access._is_gated", lambda t, c: False)
        monkeypatch.setattr("analyze_access._find_memory_dir", lambda cwd: None)

        result = main(["--candidates", "--format=context"])
        assert result == 0
        out = capsys.readouterr().out.strip()
        assert "[kb-monitor]" in out

    def test_context_format_empty(self, tmp_path, monkeypatch, capsys):
        """No candidates, no health issues — empty output."""
        setup_kb_config(tmp_path)
        setup_access_log(tmp_path, [])
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        monkeypatch.setattr("analyze_access._find_memory_dir", lambda cwd: None)

        result = main(["--candidates", "--health", "--format=context"])
        assert result == 0
        assert capsys.readouterr().out == ""

    def test_default_includes_all(self, tmp_path, monkeypatch, capsys):
        """No flags specified — defaults to all three."""
        setup_kb_config(tmp_path)
        setup_access_log(tmp_path, [make_log_entry("t")])
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        monkeypatch.setattr("analyze_access._find_memory_dir", lambda cwd: None)

        result = main([])
        assert result == 0
        parsed = json.loads(capsys.readouterr().out)
        assert "top_topics" in parsed
