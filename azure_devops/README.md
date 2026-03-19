# Azure DevOps Contributors Count

Count unique contributing developers across an Azure DevOps project over a configurable time window.

## Features

- **Configurable time window**: Default 90 days, adjustable with `--days`
- **Project-wide scanning**: Scans all Git repositories within a project
- **Bot exclusion**: Filter out service accounts with `--exclude-bots`
- **Continuation-token pagination**: Handles large organizations
- **Three output formats**: Text, JSON, and Markdown reports

## Quick Start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export ADO_TOKEN=your_pat_here
python3 ado_contributors_90d.py --org https://dev.azure.com/myorg --project myproject
```

## Options

| Flag | Description |
|------|-------------|
| `--org` / `-o` | Organization URL **(required)**, e.g. `https://dev.azure.com/myorg` |
| `--project` / `-p` | Project name **(required)** |
| `--token` / `-t` | PAT (overrides `ADO_TOKEN` env var) |
| `--days` / `-d` | Days to look back (default: 90) |
| `--exclude-bots` | Exclude bot/service accounts |
| `--verbose` / `-v` | Print API diagnostics to stderr |
| `--list-contributors` | Show contributor details |
| `--format` | `text`, `json`, or `markdown` |

## Token Permissions

Create a PAT with `Code (Read)` scope.

## Examples

```bash
# 30-day window with markdown report
python3 ado_contributors_90d.py --org https://dev.azure.com/myorg --project myproj --days 30 --format markdown

# JSON output, exclude bots
python3 ado_contributors_90d.py --org https://dev.azure.com/myorg --project myproj --format json --exclude-bots

# Debug with verbose mode
python3 ado_contributors_90d.py --org https://dev.azure.com/myorg --project myproj --verbose 2>debug.log
```

See the [root README](../README.md) for full documentation.
