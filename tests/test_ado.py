import json
import base64
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from ado_contributors_90d import main, ADOClient, fetch_repos


class TestCLI:
    """Tests for CLI flag parsing and validation."""

    def setup_method(self):
        self.runner = CliRunner()

    def test_help_shows_all_options(self):
        result = self.runner.invoke(main, ['--help'])
        assert result.exit_code == 0
        assert '--org' in result.output
        assert '--project' in result.output
        assert '--days' in result.output
        assert '--format' in result.output
        assert '--list-contributors' in result.output
        assert '--token' in result.output

    def test_org_is_required(self):
        result = self.runner.invoke(main, ['--project', 'proj'])
        assert result.exit_code != 0

    def test_project_is_required(self):
        result = self.runner.invoke(main, ['--org', 'https://dev.azure.com/myorg'])
        assert result.exit_code != 0

    def test_token_required(self):
        result = self.runner.invoke(main, [
            '--org', 'https://dev.azure.com/myorg',
            '--project', 'proj',
        ], env={'ADO_TOKEN': ''})
        assert result.exit_code != 0

    def test_invalid_days_zero(self):
        result = self.runner.invoke(main, [
            '--org', 'https://dev.azure.com/myorg',
            '--project', 'proj',
            '--token', 'fake',
            '--days', '0',
        ])
        assert result.exit_code != 0
        assert '--days must be at least 1' in result.output


class TestADOClient:
    """Tests for the ADOClient class."""

    def test_client_sets_basic_auth_header(self):
        client = ADOClient(token="my-pat", org_url="https://dev.azure.com/myorg")
        auth_header = client._session.headers.get('Authorization', '')
        assert auth_header.startswith('Basic ')
        decoded = base64.b64decode(auth_header.split(' ')[1]).decode()
        assert decoded == ':my-pat'

    def test_client_no_token(self):
        client = ADOClient(token=None, org_url="https://dev.azure.com/myorg")
        assert 'Authorization' not in client._session.headers

    def test_client_strips_trailing_slash(self):
        client = ADOClient(token="t", org_url="https://dev.azure.com/myorg/")
        assert client._org_url == "https://dev.azure.com/myorg"


class TestContributorDedup:
    """Tests for contributor deduplication logic."""

    @patch('ado_contributors_90d._fetch_commits')
    @patch('ado_contributors_90d.fetch_repos')
    def test_email_dedup(self, mock_repos, mock_commits):
        mock_repos.return_value = [
            {'name': 'repo1', 'id': 'id-1'},
        ]
        mock_commits.return_value = iter([
            {'author': {'email': 'alice@example.com', 'name': 'Alice'}},
            {'author': {'email': 'alice@example.com', 'name': 'Alice A'}},
        ])

        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'https://dev.azure.com/myorg',
            '--project', 'proj',
            '--token', 'fake-token',
            '--format', 'json',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['unique_contributors'] == 1

    @patch('ado_contributors_90d._fetch_commits')
    @patch('ado_contributors_90d.fetch_repos')
    def test_different_contributors(self, mock_repos, mock_commits):
        mock_repos.return_value = [
            {'name': 'repo1', 'id': 'id-1'},
        ]
        mock_commits.return_value = iter([
            {'author': {'email': 'alice@example.com', 'name': 'Alice'}},
            {'author': {'email': 'bob@example.com', 'name': 'Bob'}},
        ])

        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'https://dev.azure.com/myorg',
            '--project', 'proj',
            '--token', 'fake-token',
            '--format', 'json',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['unique_contributors'] == 2

    @patch('ado_contributors_90d._fetch_commits')
    @patch('ado_contributors_90d.fetch_repos')
    def test_name_fallback_when_no_email(self, mock_repos, mock_commits):
        mock_repos.return_value = [
            {'name': 'repo1', 'id': 'id-1'},
        ]
        mock_commits.return_value = iter([
            {'author': {'name': 'Alice NoEmail'}},
            {'author': {'name': 'Alice NoEmail'}},
        ])

        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'https://dev.azure.com/myorg',
            '--project', 'proj',
            '--token', 'fake-token',
            '--format', 'json',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['unique_contributors'] == 1


class TestDaysFlag:
    """Tests for the configurable --days flag."""

    @patch('ado_contributors_90d._fetch_commits')
    @patch('ado_contributors_90d.fetch_repos')
    def test_days_in_json_output(self, mock_repos, mock_commits):
        mock_repos.return_value = []
        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'https://dev.azure.com/myorg',
            '--project', 'proj',
            '--token', 'fake-token',
            '--format', 'json',
            '--days', '30',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['days'] == 30
        assert 'unique_contributors' in data

    @patch('ado_contributors_90d._fetch_commits')
    @patch('ado_contributors_90d.fetch_repos')
    def test_default_days_is_90(self, mock_repos, mock_commits):
        mock_repos.return_value = []
        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'https://dev.azure.com/myorg',
            '--project', 'proj',
            '--token', 'fake-token',
            '--format', 'json',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['days'] == 90

    @patch('ado_contributors_90d._fetch_commits')
    @patch('ado_contributors_90d.fetch_repos')
    def test_days_in_text_output(self, mock_repos, mock_commits):
        mock_repos.return_value = [
            {'name': 'repo1', 'id': 'id-1'},
        ]
        mock_commits.return_value = iter([])
        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'https://dev.azure.com/myorg',
            '--project', 'proj',
            '--token', 'fake-token',
            '--days', '180',
        ])
        assert result.exit_code == 0
        assert 'Contributors in last 180 days' in result.output


class TestOutputFormats:
    """Tests for text and JSON output structure."""

    @patch('ado_contributors_90d._fetch_commits')
    @patch('ado_contributors_90d.fetch_repos')
    def test_json_structure(self, mock_repos, mock_commits):
        mock_repos.return_value = []
        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'https://dev.azure.com/myorg',
            '--project', 'proj',
            '--token', 'fake-token',
            '--format', 'json',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert 'org' in data
        assert 'project' in data
        assert 'scan_date' in data
        assert 'days' in data
        assert 'unique_contributors' in data

    @patch('ado_contributors_90d._fetch_commits')
    @patch('ado_contributors_90d.fetch_repos')
    def test_text_output_structure(self, mock_repos, mock_commits):
        mock_repos.return_value = [
            {'name': 'repo1', 'id': 'id-1'},
        ]
        mock_commits.return_value = iter([])
        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'https://dev.azure.com/myorg',
            '--project', 'proj',
            '--token', 'fake-token',
        ])
        assert result.exit_code == 0
        assert 'Organization: https://dev.azure.com/myorg' in result.output
        assert 'Project: proj' in result.output
        assert 'Scan Date:' in result.output
        assert 'Contributors in last 90 days:' in result.output

    @patch('ado_contributors_90d._fetch_commits')
    @patch('ado_contributors_90d.fetch_repos')
    def test_list_contributors_json(self, mock_repos, mock_commits):
        mock_repos.return_value = [
            {'name': 'repo1', 'id': 'id-1'},
        ]
        mock_commits.return_value = iter([
            {'author': {'email': 'alice@example.com', 'name': 'Alice'}},
        ])

        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'https://dev.azure.com/myorg',
            '--project', 'proj',
            '--token', 'fake-token',
            '--format', 'json',
            '--list-contributors',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert 'contributors_details' in data
        assert len(data['contributors_details']) == 1


class TestVerboseMode:
    """Tests for --verbose flag."""

    def test_verbose_flag_in_help(self):
        result = CliRunner().invoke(main, ['--help'])
        assert result.exit_code == 0
        assert '--verbose' in result.output

    @patch('ado_contributors_90d._fetch_commits')
    @patch('ado_contributors_90d.fetch_repos')
    def test_verbose_outputs_to_stderr(self, mock_repos, mock_commits):
        mock_repos.return_value = [{'name': 'repo1', 'id': 'id-1'}]
        mock_commits.return_value = iter([])

        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, [
            '--org', 'https://dev.azure.com/myorg',
            '--project', 'proj',
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

    @patch('ado_contributors_90d._fetch_commits')
    @patch('ado_contributors_90d.fetch_repos')
    def test_bots_excluded(self, mock_repos, mock_commits):
        mock_repos.return_value = [{'name': 'repo1', 'id': 'id-1'}]
        mock_commits.return_value = iter([
            {'author': {'email': 'bot@noreply.com', 'name': 'dependabot[bot]'}},
            {'author': {'email': 'alice@example.com', 'name': 'Alice'}},
        ])

        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'https://dev.azure.com/myorg',
            '--project', 'proj',
            '--token', 'fake-token',
            '--format', 'json',
            '--exclude-bots',
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data['unique_contributors'] == 1

    @patch('ado_contributors_90d._fetch_commits')
    @patch('ado_contributors_90d.fetch_repos')
    def test_bots_included_by_default(self, mock_repos, mock_commits):
        mock_repos.return_value = [{'name': 'repo1', 'id': 'id-1'}]
        mock_commits.return_value = iter([
            {'author': {'email': 'bot@noreply.com', 'name': 'dependabot[bot]'}},
            {'author': {'email': 'alice@example.com', 'name': 'Alice'}},
        ])

        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'https://dev.azure.com/myorg',
            '--project', 'proj',
            '--token', 'fake-token',
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

    @patch('ado_contributors_90d._fetch_commits')
    @patch('ado_contributors_90d.fetch_repos')
    def test_markdown_output_structure(self, mock_repos, mock_commits):
        mock_repos.return_value = []
        mock_commits.return_value = iter([])

        runner = CliRunner()
        result = runner.invoke(main, [
            '--org', 'https://dev.azure.com/myorg',
            '--project', 'proj',
            '--token', 'fake-token',
            '--format', 'markdown',
        ])
        assert result.exit_code == 0
        assert '# Contributors Report' in result.output
        assert '| Field | Value |' in result.output
        assert 'Unique Contributors' in result.output
