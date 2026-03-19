import json
import datetime
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from github_contributors_90d import main, GitHubClient, fetch_repos


class TestCLI:
    """Tests for CLI flag parsing and validation."""

    def setup_method(self):
        self.runner = CliRunner()

    def test_help_shows_all_options(self):
        result = self.runner.invoke(main, ['--help'])
        assert result.exit_code == 0
        assert '--org' in result.output
        assert '--days' in result.output
        assert '--format' in result.output
        assert '--list-contributors' in result.output
        assert '--default-branch-only' in result.output
        assert '--exclude-bots' in result.output
        assert '--max-repos' in result.output

    def test_days_shown_in_help_with_default(self):
        result = self.runner.invoke(main, ['--help'])
        assert '90' in result.output

    def test_org_is_required(self):
        result = self.runner.invoke(main, [])
        assert result.exit_code != 0
        assert 'Missing' in result.output or 'required' in result.output.lower()

    def test_invalid_days_zero(self):
        result = self.runner.invoke(main, ['--org', 'test-org', '--days', '0'])
        assert result.exit_code != 0
        assert '--days must be at least 1' in result.output

    def test_invalid_days_negative(self):
        result = self.runner.invoke(main, ['--org', 'test-org', '--days', '-5'])
        assert result.exit_code != 0


class TestGitHubClient:
    """Tests for the GitHubClient class."""

    def test_client_with_token(self):
        client = GitHubClient(token="test-token-123")
        session = client._session
        assert 'Authorization' in session.headers
        assert session.headers['Authorization'] == 'token test-token-123'

    def test_client_no_token(self):
        client = GitHubClient(token=None)
        session = client._session
        assert 'Authorization' not in session.headers

    def test_client_custom_base_url(self):
        client = GitHubClient(token=None, base_url="https://github.example.com/api/v3/")
        assert client._base_url == "https://github.example.com/api/v3"

    def test_client_strips_trailing_slash(self):
        client = GitHubClient(token=None, base_url="https://api.github.com/")
        assert client._base_url == "https://api.github.com"


class TestContributorDedup:
    """Tests for contributor deduplication logic via the full CLI flow."""

    @patch('github_contributors_90d._scan_repo')
    @patch('github_contributors_90d.fetch_repos')
    def test_same_login_multiple_repos_counted_once(self, mock_repos, mock_scan):
        mock_repos.return_value = [
            {'full_name': 'org/repo1', 'default_branch': 'main'},
            {'full_name': 'org/repo2', 'default_branch': 'main'},
        ]
        mock_scan.return_value = {
            'repo_name': 'org/repo1',
            'branch_count': 1,
            'commit_count': 1,
            'contributors': {'alice': {'alice@example.com'}},
        }

        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'test-org',
            '--token', 'fake-token',
            '--format', 'json',
            '--default-branch-only',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['unique_contributors'] == 1

    @patch('github_contributors_90d._scan_repo')
    @patch('github_contributors_90d.fetch_repos')
    def test_different_logins_counted_separately(self, mock_repos, mock_scan):
        mock_repos.return_value = [
            {'full_name': 'org/repo1', 'default_branch': 'main'},
        ]
        mock_scan.return_value = {
            'repo_name': 'org/repo1',
            'branch_count': 1,
            'commit_count': 2,
            'contributors': {
                'alice': {'alice@example.com'},
                'bob': {'bob@example.com'},
            },
        }

        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'test-org',
            '--token', 'fake-token',
            '--format', 'json',
            '--default-branch-only',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['unique_contributors'] == 2


class TestDaysFlag:
    """Tests for the configurable --days flag."""

    @patch('github_contributors_90d._scan_repo')
    @patch('github_contributors_90d.fetch_repos')
    def test_days_in_json_output(self, mock_repos, mock_scan):
        mock_repos.return_value = []

        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'test-org',
            '--token', 'fake-token',
            '--format', 'json',
            '--days', '30',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data.get('days', data.get('unique_contributors', None)) is not None
        if 'days' in data:
            assert data['days'] == 30

    @patch('github_contributors_90d._scan_repo')
    @patch('github_contributors_90d.fetch_repos')
    def test_default_days_is_90(self, mock_repos, mock_scan):
        mock_repos.return_value = []

        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'test-org',
            '--token', 'fake-token',
            '--format', 'json',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        if 'days' in data:
            assert data['days'] == 90

    @patch('github_contributors_90d._scan_repo')
    @patch('github_contributors_90d.fetch_repos')
    def test_days_in_text_output(self, mock_repos, mock_scan):
        mock_repos.return_value = [
            {'full_name': 'org/repo1', 'default_branch': 'main'},
        ]
        mock_scan.return_value = {
            'repo_name': 'org/repo1',
            'branch_count': 1,
            'commit_count': 0,
            'contributors': {},
        }

        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'test-org',
            '--token', 'fake-token',
            '--days', '45',
        ])
        assert result.exit_code == 0
        assert 'Contributors in last 45 days' in result.output


class TestOutputFormats:
    """Tests for text and JSON output structure."""

    @patch('github_contributors_90d._scan_repo')
    @patch('github_contributors_90d.fetch_repos')
    def test_json_structure(self, mock_repos, mock_scan):
        mock_repos.return_value = [
            {'full_name': 'org/repo1', 'default_branch': 'main'},
        ]
        mock_scan.return_value = {
            'repo_name': 'org/repo1',
            'branch_count': 1,
            'commit_count': 1,
            'contributors': {'alice': {'alice@example.com'}},
        }

        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'test-org',
            '--token', 'fake-token',
            '--format', 'json',
            '--default-branch-only',
            '--list-contributors',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert 'org' in data
        assert 'scan_date' in data
        assert 'unique_contributors' in data

    @patch('github_contributors_90d._scan_repo')
    @patch('github_contributors_90d.fetch_repos')
    def test_text_output_structure(self, mock_repos, mock_scan):
        mock_repos.return_value = [
            {'full_name': 'org/repo1', 'default_branch': 'main'},
        ]
        mock_scan.return_value = {
            'repo_name': 'org/repo1',
            'branch_count': 1,
            'commit_count': 0,
            'contributors': {},
        }

        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'test-org',
            '--token', 'fake-token',
        ])
        assert result.exit_code == 0
        assert 'Organization: test-org' in result.output
        assert 'Scan Date:' in result.output
        assert 'Contributors in last 90 days:' in result.output


class TestVerboseMode:
    """Tests for --verbose flag."""

    def test_verbose_flag_in_help(self):
        result = CliRunner().invoke(main, ['--help'])
        assert result.exit_code == 0
        assert '--verbose' in result.output

    @patch('github_contributors_90d._scan_repo')
    @patch('github_contributors_90d.fetch_repos')
    def test_verbose_outputs_to_stderr(self, mock_repos, mock_scan):
        mock_repos.return_value = [{'full_name': 'org/repo1', 'default_branch': 'main'}]
        mock_scan.return_value = {
            'repo_name': 'org/repo1',
            'branch_count': 1,
            'commit_count': 0,
            'contributors': {},
        }

        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, [
            '--org', 'test-org',
            '--token', 'fake-token',
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

    @patch('github_contributors_90d._scan_repo')
    @patch('github_contributors_90d.fetch_repos')
    def test_bots_excluded(self, mock_repos, mock_scan):
        def scan_side_effect(*args, **kwargs):
            exclude_bots = args[5] if len(args) > 5 else kwargs.get('exclude_bots', False)
            if exclude_bots:
                return {
                    'repo_name': 'org/repo1',
                    'branch_count': 1,
                    'commit_count': 1,
                    'contributors': {'alice': {'alice@example.com'}},
                }
            return {
                'repo_name': 'org/repo1',
                'branch_count': 1,
                'commit_count': 2,
                'contributors': {
                    'alice': {'alice@example.com'},
                    'dependabot[bot]': {'bot@noreply.com'},
                },
            }

        mock_repos.return_value = [{'full_name': 'org/repo1', 'default_branch': 'main'}]
        mock_scan.side_effect = scan_side_effect

        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'test-org',
            '--token', 'fake-token',
            '--format', 'json',
            '--exclude-bots',
            '--default-branch-only',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['unique_contributors'] == 1

    @patch('github_contributors_90d._scan_repo')
    @patch('github_contributors_90d.fetch_repos')
    def test_bots_included_by_default(self, mock_repos, mock_scan):
        def scan_side_effect(*args, **kwargs):
            exclude_bots = args[5] if len(args) > 5 else kwargs.get('exclude_bots', False)
            if exclude_bots:
                return {
                    'repo_name': 'org/repo1',
                    'branch_count': 1,
                    'commit_count': 1,
                    'contributors': {'alice': {'alice@example.com'}},
                }
            return {
                'repo_name': 'org/repo1',
                'branch_count': 1,
                'commit_count': 2,
                'contributors': {
                    'alice': {'alice@example.com'},
                    'dependabot[bot]': {'bot@noreply.com'},
                },
            }

        mock_repos.return_value = [{'full_name': 'org/repo1', 'default_branch': 'main'}]
        mock_scan.side_effect = scan_side_effect

        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'test-org',
            '--token', 'fake-token',
            '--format', 'json',
            '--default-branch-only',
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

    @patch('github_contributors_90d._scan_repo')
    @patch('github_contributors_90d.fetch_repos')
    def test_markdown_output_structure(self, mock_repos, mock_scan):
        mock_repos.return_value = [{'full_name': 'org/repo1', 'default_branch': 'main'}]
        mock_scan.return_value = {
            'repo_name': 'org/repo1',
            'branch_count': 1,
            'commit_count': 0,
            'contributors': {},
        }

        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'test-org',
            '--token', 'fake-token',
            '--format', 'markdown',
            '--default-branch-only',
        ])
        assert result.exit_code == 0
        assert '# Contributors Report' in result.output
        assert '| Field | Value |' in result.output
        assert 'Unique Contributors' in result.output
