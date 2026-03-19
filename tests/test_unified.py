"""Tests for the unified cross-platform contributors_count.py runner."""
import json
import os
import sys
import tempfile

import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from contributors_count import (
    main, _cross_dedup, _UnionFind, _load_config, PlatformResult, _elapsed,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_config(tmp_dir, cfg):
    path = os.path.join(tmp_dir, "platforms.json")
    with open(path, "w") as f:
        json.dump(cfg, f)
    return path


def _make_result(platform, label, contributors, repos=3, commits=100):
    return PlatformResult(
        platform=platform,
        label=label,
        contributors=contributors,
        repos_scanned=repos,
        total_commits=commits,
        skipped_repos=[],
        elapsed=1.5,
    )


# ---------------------------------------------------------------------------
# UnionFind
# ---------------------------------------------------------------------------

class TestUnionFind:
    def test_singletons(self):
        uf = _UnionFind()
        uf.find("a")
        uf.find("b")
        groups = uf.groups()
        assert len(groups) == 2

    def test_union_merges(self):
        uf = _UnionFind()
        uf.find("a")
        uf.find("b")
        uf.union("a", "b")
        groups = uf.groups()
        assert len(groups) == 1
        members = list(groups.values())[0]
        assert set(members) == {"a", "b"}

    def test_transitive_union(self):
        uf = _UnionFind()
        uf.union("a", "b")
        uf.union("b", "c")
        groups = uf.groups()
        assert len(groups) == 1
        members = list(groups.values())[0]
        assert set(members) == {"a", "b", "c"}

    def test_no_cross_union(self):
        uf = _UnionFind()
        uf.union("a", "b")
        uf.union("c", "d")
        groups = uf.groups()
        assert len(groups) == 2


# ---------------------------------------------------------------------------
# Cross-platform deduplication
# ---------------------------------------------------------------------------

class TestCrossDedup:
    def test_no_overlap(self):
        """Contributors on different platforms with no shared emails stay separate."""
        results = [
            _make_result("GitHub", "GH", {
                "alice": {"alice@work.com"},
            }),
            _make_result("GitLab", "GL", {
                "bob": {"bob@work.com"},
            }),
        ]
        count, merged = _cross_dedup(results)
        assert count == 2

    def test_email_overlap_merges(self):
        """Same email on different platforms merges to one contributor."""
        results = [
            _make_result("GitHub", "GH", {
                "alice": {"alice@work.com"},
            }),
            _make_result("GitLab", "GL", {
                "alice-gl": {"alice@work.com"},
            }),
        ]
        count, merged = _cross_dedup(results)
        assert count == 1
        assert len(merged[0]["members"]) == 2
        assert "alice@work.com" in merged[0]["emails"]

    def test_transitive_email_merge(self):
        """A shares email with B, B shares different email with C -> all merge."""
        results = [
            _make_result("GitHub", "GH", {
                "alice": {"shared@work.com"},
            }),
            _make_result("GitLab", "GL", {
                "alice-gl": {"shared@work.com", "alice@personal.com"},
            }),
            _make_result("Azure DevOps", "ADO", {
                "alice-ado": {"alice@personal.com"},
            }),
        ]
        count, merged = _cross_dedup(results)
        assert count == 1

    def test_no_emails_stay_separate(self):
        """Contributors with no emails can't be cross-deduped."""
        results = [
            _make_result("GitHub", "GH", {
                "alice": set(),
            }),
            _make_result("GitLab", "GL", {
                "alice": set(),
            }),
        ]
        count, merged = _cross_dedup(results)
        assert count == 2

    def test_mixed_overlap_and_unique(self):
        """Mix of shared and unique contributors."""
        results = [
            _make_result("GitHub", "GH", {
                "alice": {"alice@work.com"},
                "bob": {"bob@work.com"},
            }),
            _make_result("GitLab", "GL", {
                "alice-gl": {"alice@work.com"},
                "charlie": {"charlie@work.com"},
            }),
        ]
        count, merged = _cross_dedup(results)
        assert count == 3  # alice merged, bob unique, charlie unique

    def test_single_platform(self):
        """Single platform: no cross-dedup needed, count stays the same."""
        results = [
            _make_result("GitHub", "GH", {
                "alice": {"alice@work.com"},
                "bob": {"bob@work.com"},
            }),
        ]
        count, merged = _cross_dedup(results)
        assert count == 2

    def test_empty_results(self):
        count, merged = _cross_dedup([])
        assert count == 0
        assert merged == []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class TestCLI:
    def test_help_shows_all_options(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        for flag in ["--config", "--days", "--exclude-bots", "--verbose",
                      "--format", "--list-contributors"]:
            assert flag in result.output

    def test_config_required(self):
        runner = CliRunner()
        result = runner.invoke(main, [])
        assert result.exit_code != 0

    def test_invalid_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = _write_config(tmp, {"github": {"org": "test"}})
            runner = CliRunner()
            result = runner.invoke(main, ["--config", cfg_path, "--days", "0"])
            assert result.exit_code != 0
            assert "--days must be at least 1" in result.output

    def test_no_valid_platforms(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = _write_config(tmp, {"invalid_platform": {}})
            runner = CliRunner()
            result = runner.invoke(main, ["--config", cfg_path])
            assert result.exit_code != 0
            assert "no valid platforms" in result.output


# ---------------------------------------------------------------------------
# End-to-end with mocked scanners
# ---------------------------------------------------------------------------

class TestEndToEnd:
    """Test full pipeline by mocking the platform scanner functions."""

    def _mock_scanner(self, platform, label, contributors):
        def scanner(config, days, exclude_bots, vlog):
            return _make_result(platform, label, contributors)
        return scanner

    @patch("contributors_count._SCANNERS")
    def test_text_output(self, mock_scanners):
        mock_scanners.__contains__ = lambda self, k: k in {"github", "gitlab"}
        mock_scanners.__getitem__ = lambda self, k: {
            "github": self._gh, "gitlab": self._gl,
        }[k]
        mock_scanners.__iter__ = lambda self: iter(["github", "gitlab"])
        mock_scanners._gh = self._mock_scanner(
            "GitHub", "GH: org", {"alice": {"a@x.com"}, "bob": {"b@x.com"}},
        )
        mock_scanners._gl = self._mock_scanner(
            "GitLab", "GL: url", {"alice-gl": {"a@x.com"}, "charlie": {"c@x.com"}},
        )

        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = _write_config(tmp, {
                "github": {"org": "test"},
                "gitlab": {"url": "https://gitlab.com"},
            })
            runner = CliRunner()
            result = runner.invoke(main, ["--config", cfg_path])
            assert result.exit_code == 0
            assert "Cross-Platform Contributors Report" in result.output
            assert "Unique Contributors:" in result.output

    @patch("contributors_count._SCANNERS")
    def test_json_output(self, mock_scanners):
        mock_scanners.__contains__ = lambda self, k: k == "github"
        mock_scanners.__getitem__ = lambda self, k: self._gh
        mock_scanners.__iter__ = lambda self: iter(["github"])
        mock_scanners._gh = self._mock_scanner(
            "GitHub", "GH: org", {"alice": {"a@x.com"}},
        )

        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = _write_config(tmp, {"github": {"org": "test"}})
            runner = CliRunner()
            result = runner.invoke(
                main, ["--config", cfg_path, "--format", "json"],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "unique_contributors_cross_platform" in data
            assert data["unique_contributors_cross_platform"] == 1
            assert "platforms" in data
            assert "GitHub" in data["platforms"]

    @patch("contributors_count._SCANNERS")
    def test_markdown_output(self, mock_scanners):
        mock_scanners.__contains__ = lambda self, k: k == "github"
        mock_scanners.__getitem__ = lambda self, k: self._gh
        mock_scanners.__iter__ = lambda self: iter(["github"])
        mock_scanners._gh = self._mock_scanner(
            "GitHub", "GH: org", {"alice": {"a@x.com"}},
        )

        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = _write_config(tmp, {"github": {"org": "test"}})
            runner = CliRunner()
            result = runner.invoke(
                main, ["--config", cfg_path, "--format", "markdown"],
            )
            assert result.exit_code == 0
            assert "# Cross-Platform Contributors Report" in result.output
            assert "| Field | Value |" in result.output


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_elapsed_seconds(self):
        assert _elapsed(45) == "45s"

    def test_elapsed_minutes(self):
        assert _elapsed(125) == "2m 5s"

    def test_load_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, {"github": {"org": "test"}})
            cfg = _load_config(path)
            assert cfg["github"]["org"] == "test"
