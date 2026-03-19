import json
import datetime
from unittest.mock import patch, MagicMock, PropertyMock

import pytest
from click.testing import CliRunner

from gitlab_contributor_count import main, parse_commit_date, process_commits


class TestCLI:
    """Tests for CLI flag parsing and validation."""

    def setup_method(self):
        self.runner = CliRunner()

    def test_help_shows_all_options(self):
        result = self.runner.invoke(main, ['--help'])
        assert result.exit_code == 0
        assert '--url' in result.output
        assert '--token' in result.output
        assert '--days' in result.output
        assert '--format' in result.output
        assert '--list-contributors' in result.output

    def test_days_shown_in_help_with_default(self):
        result = self.runner.invoke(main, ['--help'])
        assert '90' in result.output

    def test_token_required(self):
        result = self.runner.invoke(main, [], env={'GITLAB_TOKEN': ''})
        assert result.exit_code != 0

    def test_invalid_days_zero(self):
        result = self.runner.invoke(main, ['--token', 'fake', '--days', '0'])
        assert result.exit_code != 0
        assert '--days must be at least 1' in result.output


class TestParsing:
    """Tests for date parsing and commit processing."""

    def test_parse_iso_date_with_z(self):
        dt = parse_commit_date("2025-03-15T10:30:00Z")
        assert dt.year == 2025
        assert dt.month == 3
        assert dt.day == 15

    def test_parse_iso_date_without_z(self):
        dt = parse_commit_date("2025-03-15T10:30:00")
        assert dt.year == 2025
        assert dt.month == 3

    def test_parse_iso_date_with_timezone(self):
        dt = parse_commit_date("2025-03-15T10:30:00.000+00:00")
        assert dt.year == 2025


class TestContributorDedup:
    """Tests for contributor deduplication in process_commits."""

    def _make_mock_commit(self, email, name, created_at, sha="abc123", project_path="group/proj"):
        commit = MagicMock()
        commit.author_email = email
        commit.author_name = name
        commit.created_at = created_at
        commit.id = sha
        return commit

    def test_same_email_deduplicated(self):
        project = MagicMock()
        project.path_with_namespace = "group/project"
        project.commits.list.return_value = [
            self._make_mock_commit("alice@example.com", "Alice", "2025-03-15T10:00:00Z", "sha1"),
            self._make_mock_commit("alice@example.com", "Alice A", "2025-03-16T10:00:00Z", "sha2"),
        ]

        contributors = {}
        unique = {}
        process_commits(project, "2025-03-01T00:00:00Z", contributors, unique, "https://gitlab.com")
        assert len(unique) == 1

    def test_different_emails_separate(self):
        project = MagicMock()
        project.path_with_namespace = "group/project"
        project.commits.list.return_value = [
            self._make_mock_commit("alice@example.com", "Alice", "2025-03-15T10:00:00Z", "sha1"),
            self._make_mock_commit("bob@example.com", "Bob", "2025-03-16T10:00:00Z", "sha2"),
        ]

        contributors = {}
        unique = {}
        process_commits(project, "2025-03-01T00:00:00Z", contributors, unique, "https://gitlab.com")
        assert len(unique) == 2

    def test_fallback_to_name_when_no_email(self):
        project = MagicMock()
        project.path_with_namespace = "group/project"
        project.commits.list.return_value = [
            self._make_mock_commit(None, "Alice NoEmail", "2025-03-15T10:00:00Z", "sha1"),
            self._make_mock_commit(None, "Alice NoEmail", "2025-03-16T10:00:00Z", "sha2"),
        ]

        contributors = {}
        unique = {}
        process_commits(project, "2025-03-01T00:00:00Z", contributors, unique, "https://gitlab.com")
        assert len(unique) == 1

    def test_keeps_most_recent_commit(self):
        project = MagicMock()
        project.path_with_namespace = "group/project"
        project.commits.list.return_value = [
            self._make_mock_commit("alice@example.com", "Alice", "2025-03-10T10:00:00Z", "old-sha"),
            self._make_mock_commit("alice@example.com", "Alice", "2025-03-20T10:00:00Z", "new-sha"),
        ]

        contributors = {}
        unique = {}
        process_commits(project, "2025-03-01T00:00:00Z", contributors, unique, "https://gitlab.com")
        assert unique["alice@example.com"]["sha"] == "new-sha"


class TestDaysFlag:
    """Tests for the configurable --days flag."""

    @patch('gitlab_contributor_count.gitlab.Gitlab')
    def test_days_in_json_output(self, mock_gitlab_cls):
        mock_gl = MagicMock()
        mock_gitlab_cls.return_value = mock_gl
        mock_gl.groups.list.return_value = []
        mock_gl.projects.list.return_value = []

        runner = CliRunner()
        result = runner.invoke(main, [
            '--token', 'fake-token',
            '--format', 'json',
            '--days', '30',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['days'] == 30
        assert 'unique_contributors' in data

    @patch('gitlab_contributor_count.gitlab.Gitlab')
    def test_default_days_is_90(self, mock_gitlab_cls):
        mock_gl = MagicMock()
        mock_gitlab_cls.return_value = mock_gl
        mock_gl.groups.list.return_value = []
        mock_gl.projects.list.return_value = []

        runner = CliRunner()
        result = runner.invoke(main, [
            '--token', 'fake-token',
            '--format', 'json',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['days'] == 90

    @patch('gitlab_contributor_count.gitlab.Gitlab')
    def test_days_in_text_output(self, mock_gitlab_cls):
        mock_gl = MagicMock()
        mock_gitlab_cls.return_value = mock_gl
        mock_gl.groups.list.return_value = []
        mock_gl.projects.list.return_value = []

        runner = CliRunner()
        result = runner.invoke(main, [
            '--token', 'fake-token',
            '--days', '60',
        ])
        assert result.exit_code == 0
        assert 'contributors in last 60 days' in result.output


class TestOutputFormats:
    """Tests for text and JSON output structure."""

    @patch('gitlab_contributor_count.gitlab.Gitlab')
    def test_json_structure(self, mock_gitlab_cls):
        mock_gl = MagicMock()
        mock_gitlab_cls.return_value = mock_gl
        mock_gl.groups.list.return_value = []
        mock_gl.projects.list.return_value = []

        runner = CliRunner()
        result = runner.invoke(main, [
            '--token', 'fake-token',
            '--format', 'json',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert 'gitlab_url' in data
        assert 'scan_date' in data
        assert 'days' in data
        assert 'unique_contributors' in data
        assert 'groups' in data

    @patch('gitlab_contributor_count.gitlab.Gitlab')
    def test_text_output_structure(self, mock_gitlab_cls):
        mock_gl = MagicMock()
        mock_gitlab_cls.return_value = mock_gl
        mock_gl.groups.list.return_value = []
        mock_gl.projects.list.return_value = []

        runner = CliRunner()
        result = runner.invoke(main, ['--token', 'fake-token'])
        assert result.exit_code == 0
        assert 'GitLab URL:' in result.output
        assert 'Scan Date:' in result.output
        assert 'Total unique contributors in last 90 days:' in result.output
