import json
import datetime
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from github_contributors_90d import main, GitHubClient, fetch_repos, fetch_commits


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

    def test_client_sets_auth_header(self):
        client = GitHubClient(token="test-token-123")
        assert 'Authorization' in client.session.headers
        assert client.session.headers['Authorization'] == 'token test-token-123'

    def test_client_no_token(self):
        client = GitHubClient(token=None)
        assert 'Authorization' not in client.session.headers

    def test_client_custom_base_url(self):
        client = GitHubClient(token=None, base_url="https://github.example.com/api/v3/")
        assert client.base_url == "https://github.example.com/api/v3"

    def test_client_strips_trailing_slash(self):
        client = GitHubClient(token=None, base_url="https://api.github.com/")
        assert client.base_url == "https://api.github.com"


class TestContributorDedup:
    """Tests for contributor deduplication logic via the full CLI flow."""

    @patch('github_contributors_90d.fetch_commits')
    @patch('github_contributors_90d.fetch_repos')
    def test_same_login_multiple_repos_counted_once(self, mock_repos, mock_commits):
        mock_repos.return_value = iter([
            {'full_name': 'org/repo1', 'default_branch': 'main'},
            {'full_name': 'org/repo2', 'default_branch': 'main'},
        ])

        commit_template = {
            'sha': None,
            'author': {'login': 'alice', 'type': 'User'},
            'commit': {'author': {'email': 'alice@example.com'}},
        }

        call_count = [0]
        def commits_side_effect(*args, **kwargs):
            call_count[0] += 1
            commit = dict(commit_template)
            commit['sha'] = f'sha-{call_count[0]}'
            return iter([commit])

        mock_commits.side_effect = commits_side_effect

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

    @patch('github_contributors_90d.fetch_commits')
    @patch('github_contributors_90d.fetch_repos')
    def test_different_logins_counted_separately(self, mock_repos, mock_commits):
        mock_repos.return_value = iter([
            {'full_name': 'org/repo1', 'default_branch': 'main'},
        ])

        commits = [
            {
                'sha': 'sha-1',
                'author': {'login': 'alice', 'type': 'User'},
                'commit': {'author': {'email': 'alice@example.com'}},
            },
            {
                'sha': 'sha-2',
                'author': {'login': 'bob', 'type': 'User'},
                'commit': {'author': {'email': 'bob@example.com'}},
            },
        ]
        mock_commits.return_value = iter(commits)

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

    @patch('github_contributors_90d.fetch_commits')
    @patch('github_contributors_90d.fetch_repos')
    def test_same_sha_across_branches_not_double_counted(self, mock_repos, mock_commits):
        mock_repos.return_value = iter([
            {'full_name': 'org/repo1', 'default_branch': 'main'},
        ])

        shared_commit = {
            'sha': 'same-sha-123',
            'author': {'login': 'alice', 'type': 'User'},
            'commit': {'author': {'email': 'alice@example.com'}},
        }
        mock_commits.return_value = iter([shared_commit, shared_commit])

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


class TestBotExclusion:
    """Tests for the --exclude-bots flag."""

    @patch('github_contributors_90d.fetch_commits')
    @patch('github_contributors_90d.fetch_repos')
    def test_bots_excluded_by_type(self, mock_repos, mock_commits):
        mock_repos.return_value = iter([
            {'full_name': 'org/repo1', 'default_branch': 'main'},
        ])
        mock_commits.return_value = iter([
            {
                'sha': 'sha-1',
                'author': {'login': 'dependabot[bot]', 'type': 'Bot'},
                'commit': {'author': {'email': 'dependabot@github.com'}},
            },
            {
                'sha': 'sha-2',
                'author': {'login': 'alice', 'type': 'User'},
                'commit': {'author': {'email': 'alice@example.com'}},
            },
        ])

        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'test-org',
            '--token', 'fake-token',
            '--format', 'json',
            '--default-branch-only',
            '--exclude-bots',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['unique_contributors'] == 1

    @patch('github_contributors_90d.fetch_commits')
    @patch('github_contributors_90d.fetch_repos')
    def test_bots_included_by_default(self, mock_repos, mock_commits):
        mock_repos.return_value = iter([
            {'full_name': 'org/repo1', 'default_branch': 'main'},
        ])
        mock_commits.return_value = iter([
            {
                'sha': 'sha-1',
                'author': {'login': 'dependabot[bot]', 'type': 'Bot'},
                'commit': {'author': {'email': 'dependabot@github.com'}},
            },
            {
                'sha': 'sha-2',
                'author': {'login': 'alice', 'type': 'User'},
                'commit': {'author': {'email': 'alice@example.com'}},
            },
        ])

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

    @patch('github_contributors_90d.fetch_commits')
    @patch('github_contributors_90d.fetch_repos')
    def test_days_in_json_output(self, mock_repos, mock_commits):
        mock_repos.return_value = iter([])
        mock_commits.return_value = iter([])

        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'test-org',
            '--token', 'fake-token',
            '--format', 'json',
            '--days', '30',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['days'] == 30
        assert 'unique_contributors' in data

    @patch('github_contributors_90d.fetch_commits')
    @patch('github_contributors_90d.fetch_repos')
    def test_default_days_is_90(self, mock_repos, mock_commits):
        mock_repos.return_value = iter([])
        mock_commits.return_value = iter([])

        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'test-org',
            '--token', 'fake-token',
            '--format', 'json',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['days'] == 90

    @patch('github_contributors_90d.fetch_commits')
    @patch('github_contributors_90d.fetch_repos')
    def test_days_in_text_output(self, mock_repos, mock_commits):
        mock_repos.return_value = iter([])
        mock_commits.return_value = iter([])

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

    @patch('github_contributors_90d.fetch_commits')
    @patch('github_contributors_90d.fetch_repos')
    def test_json_structure(self, mock_repos, mock_commits):
        mock_repos.return_value = iter([
            {'full_name': 'org/repo1', 'default_branch': 'main'},
        ])
        mock_commits.return_value = iter([
            {
                'sha': 'sha-1',
                'author': {'login': 'alice', 'type': 'User'},
                'commit': {'author': {'email': 'alice@example.com'}},
            },
        ])

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
        assert 'days' in data
        assert 'unique_contributors' in data
        assert 'contributors_details' in data
        assert len(data['contributors_details']) == 1
        assert data['contributors_details'][0]['login'] == 'alice'

    @patch('github_contributors_90d.fetch_commits')
    @patch('github_contributors_90d.fetch_repos')
    def test_text_output_structure(self, mock_repos, mock_commits):
        mock_repos.return_value = iter([])

        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'test-org',
            '--token', 'fake-token',
        ])
        assert result.exit_code == 0
        assert 'Organization: test-org' in result.output
        assert 'Scan Date:' in result.output
        assert 'Repositories scanned:' in result.output
        assert 'Contributors in last 90 days:' in result.output
