import json
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from bitbucket_contributors_90d import main, BitbucketClient, fetch_repos


class TestCLI:
    """Tests for CLI flag parsing and validation."""

    def setup_method(self):
        self.runner = CliRunner()

    def test_help_shows_all_options(self):
        result = self.runner.invoke(main, ['--help'])
        assert result.exit_code == 0
        assert '--workspace' in result.output
        assert '--days' in result.output
        assert '--format' in result.output
        assert '--list-contributors' in result.output
        assert '--user' in result.output
        assert '--password' in result.output

    def test_workspace_is_required(self):
        result = self.runner.invoke(main, [])
        assert result.exit_code != 0

    def test_credentials_required(self):
        result = self.runner.invoke(main, [
            '--workspace', 'test-ws',
        ], env={'BITBUCKET_USER': '', 'BITBUCKET_PASSWORD': ''})
        assert result.exit_code != 0

    def test_invalid_days_zero(self):
        result = self.runner.invoke(main, [
            '--workspace', 'test-ws',
            '--user', 'u', '--password', 'p',
            '--days', '0',
        ])
        assert result.exit_code != 0
        assert '--days must be at least 1' in result.output


class TestBitbucketClient:
    """Tests for the BitbucketClient class."""

    def test_client_sets_basic_auth(self):
        client = BitbucketClient(user="testuser", password="testpass")
        assert client._session.auth == ("testuser", "testpass")

    def test_client_strips_trailing_slash(self):
        client = BitbucketClient(user="u", password="p", base_url="https://api.bitbucket.org/2.0/")
        assert client._base_url == "https://api.bitbucket.org/2.0"


class TestContributorDedup:
    """Tests for contributor deduplication logic."""

    @patch('bitbucket_contributors_90d._fetch_commits')
    @patch('bitbucket_contributors_90d.fetch_repos')
    def test_account_id_dedup(self, mock_repos, mock_commits):
        mock_repos.return_value = [
            {'name': 'repo1', 'slug': 'repo1'},
        ]
        mock_commits.return_value = iter([
            {
                'author': {
                    'raw': 'Alice <alice@example.com>',
                    'user': {'account_id': 'acc-123', 'display_name': 'Alice'},
                },
            },
            {
                'author': {
                    'raw': 'Alice A <alice.a@example.com>',
                    'user': {'account_id': 'acc-123', 'display_name': 'Alice'},
                },
            },
        ])

        runner = CliRunner()
        result = runner.invoke(main, [
            '--workspace', 'test-ws',
            '--user', 'u', '--password', 'p',
            '--format', 'json',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['unique_contributors'] == 1

    @patch('bitbucket_contributors_90d._fetch_commits')
    @patch('bitbucket_contributors_90d.fetch_repos')
    def test_email_fallback_when_no_account_id(self, mock_repos, mock_commits):
        mock_repos.return_value = [
            {'name': 'repo1', 'slug': 'repo1'},
        ]
        mock_commits.return_value = iter([
            {
                'author': {
                    'raw': 'Alice <alice@example.com>',
                    'user': {},
                },
            },
            {
                'author': {
                    'raw': 'Bob <bob@example.com>',
                    'user': {},
                },
            },
        ])

        runner = CliRunner()
        result = runner.invoke(main, [
            '--workspace', 'test-ws',
            '--user', 'u', '--password', 'p',
            '--format', 'json',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['unique_contributors'] == 2

    @patch('bitbucket_contributors_90d._fetch_commits')
    @patch('bitbucket_contributors_90d.fetch_repos')
    def test_raw_name_fallback_when_no_email(self, mock_repos, mock_commits):
        mock_repos.return_value = [
            {'name': 'repo1', 'slug': 'repo1'},
        ]
        mock_commits.return_value = iter([
            {
                'author': {
                    'raw': 'Alice NoEmail',
                    'user': {},
                },
            },
        ])

        runner = CliRunner()
        result = runner.invoke(main, [
            '--workspace', 'test-ws',
            '--user', 'u', '--password', 'p',
            '--format', 'json',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['unique_contributors'] == 1


class TestDaysFlag:
    """Tests for the configurable --days flag."""

    @patch('bitbucket_contributors_90d._fetch_commits')
    @patch('bitbucket_contributors_90d.fetch_repos')
    def test_days_in_json_output(self, mock_repos, mock_commits):
        mock_repos.return_value = []
        runner = CliRunner()
        result = runner.invoke(main, [
            '--workspace', 'test-ws',
            '--user', 'u', '--password', 'p',
            '--format', 'json',
            '--days', '30',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['days'] == 30
        assert 'unique_contributors' in data

    @patch('bitbucket_contributors_90d._fetch_commits')
    @patch('bitbucket_contributors_90d.fetch_repos')
    def test_default_days_is_90(self, mock_repos, mock_commits):
        mock_repos.return_value = []
        runner = CliRunner()
        result = runner.invoke(main, [
            '--workspace', 'test-ws',
            '--user', 'u', '--password', 'p',
            '--format', 'json',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['days'] == 90

    @patch('bitbucket_contributors_90d._fetch_commits')
    @patch('bitbucket_contributors_90d.fetch_repos')
    def test_days_in_text_output(self, mock_repos, mock_commits):
        mock_repos.return_value = [
            {'name': 'repo1', 'slug': 'repo1'},
        ]
        mock_commits.return_value = iter([])
        runner = CliRunner()
        result = runner.invoke(main, [
            '--workspace', 'test-ws',
            '--user', 'u', '--password', 'p',
            '--days', '14',
        ])
        assert result.exit_code == 0
        assert 'Contributors in last 14 days' in result.output


class TestOutputFormats:
    """Tests for text and JSON output structure."""

    @patch('bitbucket_contributors_90d._fetch_commits')
    @patch('bitbucket_contributors_90d.fetch_repos')
    def test_json_structure(self, mock_repos, mock_commits):
        mock_repos.return_value = []
        runner = CliRunner()
        result = runner.invoke(main, [
            '--workspace', 'test-ws',
            '--user', 'u', '--password', 'p',
            '--format', 'json',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert 'workspace' in data
        assert 'scan_date' in data
        assert 'days' in data
        assert 'unique_contributors' in data

    @patch('bitbucket_contributors_90d._fetch_commits')
    @patch('bitbucket_contributors_90d.fetch_repos')
    def test_text_output_structure(self, mock_repos, mock_commits):
        mock_repos.return_value = [
            {'name': 'repo1', 'slug': 'repo1'},
        ]
        mock_commits.return_value = iter([])
        runner = CliRunner()
        result = runner.invoke(main, [
            '--workspace', 'test-ws',
            '--user', 'u', '--password', 'p',
        ])
        assert result.exit_code == 0
        assert 'Workspace: test-ws' in result.output
        assert 'Scan Date:' in result.output
        assert 'Repositories scanned:' in result.output
        assert 'Contributors in last 90 days:' in result.output


class TestVerboseMode:
    """Tests for --verbose flag."""

    def test_verbose_flag_in_help(self):
        result = CliRunner().invoke(main, ['--help'])
        assert result.exit_code == 0
        assert '--verbose' in result.output

    @patch('bitbucket_contributors_90d._fetch_commits')
    @patch('bitbucket_contributors_90d.fetch_repos')
    def test_verbose_outputs_to_stderr(self, mock_repos, mock_commits):
        mock_repos.return_value = [{'name': 'repo1', 'slug': 'repo1'}]
        mock_commits.return_value = iter([])

        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, [
            '--workspace', 'test-ws',
            '--user', 'u', '--password', 'p',
            '--format', 'json',
            '--verbose',
        ])
        assert result.exit_code == 0
        assert '[verbose]' in result.stderr


class TestBotExclusion:
    """Tests for --exclude-bots flag."""

    def test_exclude_bots_flag_in_help(self):
        result = CliRunner().invoke(main, ['--help'])
        assert result.exit_code == 0
        assert '--exclude-bots' in result.output

    @patch('bitbucket_contributors_90d._fetch_commits')
    @patch('bitbucket_contributors_90d.fetch_repos')
    def test_bots_excluded(self, mock_repos, mock_commits):
        mock_repos.return_value = [{'name': 'repo1', 'slug': 'repo1'}]
        mock_commits.return_value = iter([
            {'author': {'raw': 'dependabot[bot] <bot@noreply.com>', 'user': {}}},
            {'author': {'raw': 'Alice <alice@example.com>', 'user': {}}},
        ])

        runner = CliRunner()
        result = runner.invoke(main, [
            '--workspace', 'test-ws',
            '--user', 'u', '--password', 'p',
            '--format', 'json',
            '--exclude-bots',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['unique_contributors'] == 1

    @patch('bitbucket_contributors_90d._fetch_commits')
    @patch('bitbucket_contributors_90d.fetch_repos')
    def test_bots_included_by_default(self, mock_repos, mock_commits):
        mock_repos.return_value = [{'name': 'repo1', 'slug': 'repo1'}]
        mock_commits.return_value = iter([
            {'author': {'raw': 'dependabot[bot] <bot@noreply.com>', 'user': {}}},
            {'author': {'raw': 'Alice <alice@example.com>', 'user': {}}},
        ])

        runner = CliRunner()
        result = runner.invoke(main, [
            '--workspace', 'test-ws',
            '--user', 'u', '--password', 'p',
            '--format', 'json',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['unique_contributors'] == 2


class TestMarkdownOutput:
    """Tests for --format markdown output."""

    def test_markdown_format_in_help(self):
        result = CliRunner().invoke(main, ['--help'])
        assert result.exit_code == 0
        assert 'markdown' in result.output

    @patch('bitbucket_contributors_90d._fetch_commits')
    @patch('bitbucket_contributors_90d.fetch_repos')
    def test_markdown_output_structure(self, mock_repos, mock_commits):
        mock_repos.return_value = []
        mock_commits.return_value = iter([])

        runner = CliRunner()
        result = runner.invoke(main, [
            '--workspace', 'test-ws',
            '--user', 'u', '--password', 'p',
            '--format', 'markdown',
        ])
        assert result.exit_code == 0
        assert '# Contributors Report' in result.output
        assert '| Field | Value |' in result.output
        assert 'Unique Contributors' in result.output
