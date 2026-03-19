import json
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from bitbucket_server_contributors_90d import main, BitbucketServerClient, fetch_repos


class TestCLI:
    """Tests for CLI flag parsing and validation."""

    def setup_method(self):
        self.runner = CliRunner()

    def test_help_shows_all_options(self):
        result = self.runner.invoke(main, ['--help'])
        assert result.exit_code == 0
        assert '--project' in result.output
        assert '--url' in result.output
        assert '--days' in result.output
        assert '--format' in result.output
        assert '--list-contributors' in result.output

    def test_project_is_required(self):
        result = self.runner.invoke(main, ['--url', 'https://bb.example.com'])
        assert result.exit_code != 0

    def test_url_is_required(self):
        result = self.runner.invoke(main, ['--project', 'PROJ'])
        assert result.exit_code != 0

    def test_credentials_required(self):
        result = self.runner.invoke(main, [
            '--project', 'PROJ',
            '--url', 'https://bb.example.com',
        ], env={'BITBUCKET_USER': '', 'BITBUCKET_PASSWORD': ''})
        assert result.exit_code != 0

    def test_invalid_days_zero(self):
        result = self.runner.invoke(main, [
            '--project', 'PROJ',
            '--url', 'https://bb.example.com',
            '--user', 'u', '--password', 'p',
            '--days', '0',
        ])
        assert result.exit_code != 0
        assert '--days must be at least 1' in result.output


class TestBitbucketServerClient:
    """Tests for the BitbucketServerClient class."""

    def test_client_sets_basic_auth(self):
        client = BitbucketServerClient(
            base_url="https://bb.example.com",
            user="testuser",
            password="testpass",
        )
        assert client._session.auth == ("testuser", "testpass")

    def test_client_strips_trailing_slash(self):
        client = BitbucketServerClient(
            base_url="https://bb.example.com/",
            user="u", password="p",
        )
        assert client._base_url == "https://bb.example.com"


class TestContributorDedup:
    """Tests for contributor deduplication logic."""

    @patch('bitbucket_server_contributors_90d._fetch_commits')
    @patch('bitbucket_server_contributors_90d.fetch_repos')
    def test_email_dedup(self, mock_repos, mock_commits):
        mock_repos.return_value = [
            {'name': 'repo1', 'slug': 'repo1'},
        ]
        mock_commits.return_value = iter([
            {'author': {'emailAddress': 'alice@example.com', 'name': 'Alice'}},
            {'author': {'emailAddress': 'alice@example.com', 'name': 'Alice A'}},
        ])

        runner = CliRunner()
        result = runner.invoke(main, [
            '--project', 'PROJ',
            '--url', 'https://bb.example.com',
            '--user', 'u', '--password', 'p',
            '--format', 'json',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['unique_contributors'] == 1

    @patch('bitbucket_server_contributors_90d._fetch_commits')
    @patch('bitbucket_server_contributors_90d.fetch_repos')
    def test_name_fallback_when_no_email(self, mock_repos, mock_commits):
        mock_repos.return_value = [
            {'name': 'repo1', 'slug': 'repo1'},
        ]
        mock_commits.return_value = iter([
            {'author': {'name': 'Alice NoEmail'}},
            {'author': {'name': 'Alice NoEmail'}},
        ])

        runner = CliRunner()
        result = runner.invoke(main, [
            '--project', 'PROJ',
            '--url', 'https://bb.example.com',
            '--user', 'u', '--password', 'p',
            '--format', 'json',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['unique_contributors'] == 1

    @patch('bitbucket_server_contributors_90d._fetch_commits')
    @patch('bitbucket_server_contributors_90d.fetch_repos')
    def test_different_contributors_counted(self, mock_repos, mock_commits):
        mock_repos.return_value = [
            {'name': 'repo1', 'slug': 'repo1'},
        ]
        mock_commits.return_value = iter([
            {'author': {'emailAddress': 'alice@example.com', 'name': 'Alice'}},
            {'author': {'emailAddress': 'bob@example.com', 'name': 'Bob'}},
        ])

        runner = CliRunner()
        result = runner.invoke(main, [
            '--project', 'PROJ',
            '--url', 'https://bb.example.com',
            '--user', 'u', '--password', 'p',
            '--format', 'json',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['unique_contributors'] == 2


class TestDaysFlag:
    """Tests for the configurable --days flag."""

    @patch('bitbucket_server_contributors_90d._fetch_commits')
    @patch('bitbucket_server_contributors_90d.fetch_repos')
    def test_days_in_json_output(self, mock_repos, mock_commits):
        mock_repos.return_value = []
        runner = CliRunner()
        result = runner.invoke(main, [
            '--project', 'PROJ',
            '--url', 'https://bb.example.com',
            '--user', 'u', '--password', 'p',
            '--format', 'json',
            '--days', '30',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['days'] == 30
        assert 'unique_contributors' in data

    @patch('bitbucket_server_contributors_90d._fetch_commits')
    @patch('bitbucket_server_contributors_90d.fetch_repos')
    def test_default_days_is_90(self, mock_repos, mock_commits):
        mock_repos.return_value = []
        runner = CliRunner()
        result = runner.invoke(main, [
            '--project', 'PROJ',
            '--url', 'https://bb.example.com',
            '--user', 'u', '--password', 'p',
            '--format', 'json',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['days'] == 90

    @patch('bitbucket_server_contributors_90d._fetch_commits')
    @patch('bitbucket_server_contributors_90d.fetch_repos')
    def test_days_in_text_output(self, mock_repos, mock_commits):
        mock_repos.return_value = [
            {'name': 'repo1', 'slug': 'repo1'},
        ]
        mock_commits.return_value = iter([])
        runner = CliRunner()
        result = runner.invoke(main, [
            '--project', 'PROJ',
            '--url', 'https://bb.example.com',
            '--user', 'u', '--password', 'p',
            '--days', '7',
        ])
        assert result.exit_code == 0
        assert 'Contributors in last 7 days' in result.output


class TestOutputFormats:
    """Tests for text and JSON output structure."""

    @patch('bitbucket_server_contributors_90d._fetch_commits')
    @patch('bitbucket_server_contributors_90d.fetch_repos')
    def test_json_structure(self, mock_repos, mock_commits):
        mock_repos.return_value = []
        runner = CliRunner()
        result = runner.invoke(main, [
            '--project', 'PROJ',
            '--url', 'https://bb.example.com',
            '--user', 'u', '--password', 'p',
            '--format', 'json',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert 'project' in data
        assert 'scan_date' in data
        assert 'days' in data
        assert 'unique_contributors' in data

    @patch('bitbucket_server_contributors_90d._fetch_commits')
    @patch('bitbucket_server_contributors_90d.fetch_repos')
    def test_text_output_structure(self, mock_repos, mock_commits):
        mock_repos.return_value = [
            {'name': 'repo1', 'slug': 'repo1'},
        ]
        mock_commits.return_value = iter([])
        runner = CliRunner()
        result = runner.invoke(main, [
            '--project', 'PROJ',
            '--url', 'https://bb.example.com',
            '--user', 'u', '--password', 'p',
        ])
        assert result.exit_code == 0
        assert 'Project: PROJ' in result.output
        assert 'Scan Date:' in result.output
        assert 'Contributors in last 90 days:' in result.output
