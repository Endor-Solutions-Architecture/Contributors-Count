# GitHub Contributors Count

Count unique contributing developers across a GitHub organization over a configurable time window.

## Features

- **Configurable time window**: Default 90 days, adjustable with `--days`
- **All-branch scanning**: Scans all branches by default to capture feature-branch contributors
- **Default branch mode**: Optionally restrict to default branch with `--default-branch-only`
- **Bot exclusion**: Filter out bot accounts with `--exclude-bots`
- **Concurrent scanning**: 4 workers for faster execution on large orgs
- **GitHub Enterprise**: Supports GHE Server via `--base-url`
- **Three output formats**: Text, JSON, and Markdown reports

## Quick Start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export GITHUB_TOKEN=your_token_here
python3 github_contributors_90d.py --org my-org
```

## Options

| Flag | Description |
|------|-------------|
| `--org` / `-o` | GitHub organization name **(required)** |
| `--token` / `-t` | PAT (overrides `GITHUB_TOKEN` env var) |
| `--base-url` | GitHub API base URL (for Enterprise Server) |
| `--days` / `-d` | Days to look back (default: 90) |
| `--default-branch-only` | Only count commits from each repo's default branch |
| `--exclude-bots` | Exclude bot accounts |
| `--max-repos` | Limit number of repositories (useful for testing) |
| `--verbose` / `-v` | Print API diagnostics to stderr |
| `--list-contributors` | Show contributor details |
| `--format` | `text`, `json`, or `markdown` |

## Token Permissions

**Fine-grained tokens (recommended):**
- Repository Permissions: `Metadata: Read-only`, `Contents: Read-only`
- Organization Permissions: `Members: Read-only`

**Classic tokens:** `repo` scope for private repos, or no scopes for public orgs.

## Examples

```bash
# 30-day window, exclude bots, list contributors
python3 github_contributors_90d.py --org my-org --days 30 --exclude-bots --list-contributors

# JSON output for automation
python3 github_contributors_90d.py --org my-org --format json

# Markdown report
python3 github_contributors_90d.py --org my-org --format markdown > report.md

# GitHub Enterprise Server
python3 github_contributors_90d.py --org my-org --base-url https://github.mycompany.com/api/v3

# Debug with verbose mode
python3 github_contributors_90d.py --org my-org --verbose 2>debug.log
```

See the [root README](../README.md) for full documentation.
