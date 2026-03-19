# Bitbucket Contributors Count

Count unique contributing developers across a Bitbucket workspace (Cloud) or project (Server/Data Center) over a configurable time window.

## Bitbucket Cloud

### Features

- **Configurable time window**: Default 90 days, adjustable with `--days`
- **Workspace-wide scanning**: Scans all repositories within a workspace
- **Bot exclusion**: Filter out service accounts with `--exclude-bots`
- **Smart deduplication**: Uses `account_id` (best), email, or raw author string
- **Three output formats**: Text, JSON, and Markdown reports

### Quick Start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export BITBUCKET_USER=your_username
export BITBUCKET_PASSWORD=your_app_password
python3 bitbucket_contributors_90d.py --workspace my-workspace
```

### Options

| Flag | Description |
|------|-------------|
| `--workspace` / `-w` | Workspace ID/slug **(required)** |
| `--user` / `-u` | Username (overrides `BITBUCKET_USER`) |
| `--password` / `-p` | App Password (overrides `BITBUCKET_PASSWORD`) |
| `--days` / `-d` | Days to look back (default: 90) |
| `--exclude-bots` | Exclude bot/service accounts |
| `--verbose` / `-v` | Print API diagnostics to stderr |
| `--list-contributors` | Show contributor details |
| `--format` | `text`, `json`, or `markdown` |

### Token Permissions

Create an **App Password** with `Repositories: Read` permission.

---

## Bitbucket Server / Data Center

### Features

- **Configurable time window**: Default 90 days, adjustable with `--days`
- **Project-level scanning**: Scans all repos within a project
- **Bot exclusion**: Filter out service accounts with `--exclude-bots`
- **Efficient pagination**: Stops paginating commits once it reaches the time window boundary
- **Three output formats**: Text, JSON, and Markdown reports

### Quick Start

```bash
export BITBUCKET_USER=your_username
export BITBUCKET_PASSWORD=your_password
python3 bitbucket_server_contributors_90d.py --project MYPROJ --url https://bitbucket.mycompany.com
```

### Options

| Flag | Description |
|------|-------------|
| `--project` / `-p` | Project Key **(required)** |
| `--url` | Server base URL **(required)** |
| `--user` / `-u` | Username (overrides `BITBUCKET_USER`) |
| `--password` / `-pw` | Password/token (overrides `BITBUCKET_PASSWORD`) |
| `--days` / `-d` | Days to look back (default: 90) |
| `--exclude-bots` | Exclude bot/service accounts |
| `--verbose` / `-v` | Print API diagnostics to stderr |
| `--list-contributors` | Show contributor details |
| `--format` | `text`, `json`, or `markdown` |

---

## Examples

```bash
# Bitbucket Cloud: 30-day window, markdown report
python3 bitbucket_contributors_90d.py --workspace my-ws --days 30 --format markdown

# Bitbucket Server: exclude bots, JSON output
python3 bitbucket_server_contributors_90d.py --project MYPROJ --url https://bb.example.com --exclude-bots --format json

# Debug with verbose mode
python3 bitbucket_contributors_90d.py --workspace my-ws --verbose 2>debug.log
```

See the [root README](../README.md) for full documentation.
