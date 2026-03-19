# Contributors-Count

**Know exactly how many developers are committing code across your organization — on any platform.**

Contributors-Count scans GitHub, GitLab, Bitbucket (Cloud & Server), and Azure DevOps to produce a deduplicated count of unique contributors over a configurable time window. No manual spreadsheets. No double-counting across repos. One command, one answer.

---

## Why This Exists

You need to know how many developers are actively contributing code. Sounds simple — until you try:

- **Repos are scattered.** Dozens (or hundreds) of repositories, each with their own commit history.
- **People use multiple emails.** The same developer shows up as three different contributors.
- **Bots inflate the numbers.** Dependabot, Renovate, and CI service accounts aren't developers.
- **Manual counting doesn't scale.** Exporting CSVs from each repo and deduplicating in a spreadsheet is error-prone and tedious.

Contributors-Count handles all of this automatically: it walks every repository, deduplicates by identity, filters bots on request, and gives you a single number you can trust.

## Quick Start

### Single Platform

```bash
cd GitHub
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export GITHUB_TOKEN=your_token_here
python3 github_contributors_90d.py --org my-org
```

### Cross-Platform (Unified Mode)

Scan multiple platforms in a single command with cross-platform deduplication:

```bash
pip install -r requirements-test.txt  # installs all dependencies

# Create a config file (see platforms.json.example)
cp platforms.json.example platforms.json
# Edit platforms.json with your org/workspace details

python3 contributors_count.py --config platforms.json
```

The unified runner deduplicates contributors **across platforms** by shared email, so a developer who commits on both GitHub and GitLab is counted once.

```
====================================================
  Cross-Platform Contributors Report
====================================================
  Scan Date:         2026-03-19
  Time Window:       90 days
  Bots Excluded:     No
  Scan Duration:     3m 42s

  GitHub: my-org
    Repositories:    42
    Commits:         3,456
    Contributors:    67

  GitLab: https://gitlab.com
    Repositories:    18
    Commits:         1,230
    Contributors:    31

----------------------------------------------------
  Per-platform sum:  98
  Cross-platform:    12 duplicate(s) merged
  Unique Contributors: 86
====================================================
```

---

## Common Options

All scripts (including the unified runner) share these flags:

| Flag | Description |
|------|-------------|
| `--days` / `-d` | Time window in days (default: **90**) |
| `--exclude-bots` | Filter out bot and service accounts |
| `--verbose` / `-v` | Print API diagnostics to stderr |
| `--list-contributors` | Show each contributor and their email(s) |
| `--format` | Output as `text` (default), `json`, or `markdown` |

## Unified Cross-Platform Mode

For scanning multiple platforms at once with cross-platform deduplication:

### Configuration

Create a `platforms.json` file (see `platforms.json.example`):

```json
{
  "github": { "org": "my-org" },
  "gitlab": { "url": "https://gitlab.com" },
  "azure_devops": {
    "org": "https://dev.azure.com/myorg",
    "project": "myproject"
  }
}
```

Only include the platforms you want to scan. Tokens are read from environment variables (`GITHUB_TOKEN`, `GITLAB_TOKEN`, `ADO_TOKEN`, `BITBUCKET_USER`/`BITBUCKET_PASSWORD`).

### Usage

```bash
# Scan all configured platforms
python3 contributors_count.py --config platforms.json

# 30-day window, exclude bots, markdown report
python3 contributors_count.py --config platforms.json --days 30 --exclude-bots --format markdown > report.md

# JSON output with contributor list
python3 contributors_count.py --config platforms.json --format json --list-contributors
```

### Cross-Platform Deduplication

The unified runner merges contributors across platforms by shared email address using a union-find algorithm. If a developer commits as `alice` on GitHub (email: alice@work.com) and `alice-gl` on GitLab (email: alice@work.com), they're counted as one unique contributor.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for details on the deduplication strategy.

---

<details>
<summary><strong>Individual Platform Setup & Options</strong></summary>

## Github

- Counts the number of contributing developers within a configurable time window (default: 90 days) of a given GitHub Organization
- Scans all branches by default to capture contributors on feature branches (not just merged code)
- Supports filtering to only count commits from each repository's default branch with `--default-branch-only`
- Scans repositories concurrently (4 workers) for faster execution on large orgs
- Prints the name of each GitHub user along with their email addresses
- Supports GitHub Enterprise Server via `--base-url`
- A GitHub PAT is recommended for authentication (required for private orgs). The permissions needed are shown below:
    - **Fine-grained tokens (recommended):**
        - Repository Permissions
            - Metadata: Read-only
            - Contents: Read-only
        - Organization Permissions
            - Members: Read-only

### Running the script:

- Create a venv with `python3 -m venv .venv` in the directory titled `GitHub`, and activate with `source .venv/bin/activate`
- Install dependencies with `pip3 install -r requirements.txt`
- Set your GitHub token: `export GITHUB_TOKEN=your_token_here`
- Run with the command `python3 github_contributors_90d.py --org <org-name>`

### Options:

- `--org` / `-o`: GitHub organization name (required)
- `--token` / `-t`: GitHub PAT (overrides `GITHUB_TOKEN` env var)
- `--days` / `-d`: Number of days to look back (default: 90)
- `--default-branch-only`: Only count commits from each repository's default branch
- `--exclude-bots`: Exclude bot accounts from the contributor count
- `--verbose` / `-v`: Print API diagnostics to stderr
- `--list-contributors`: List individual contributors and their emails
- `--format`: Output format (`text`, `json`, or `markdown`)
- `--max-repos`: Limit number of repositories to process (useful for testing)

## GitLab

- Counts the number of contributing developers within a configurable time window (default: 90 days) across all accessible GitLab groups and projects
- Deduplicates contributors by email address across groups and standalone projects
- Avoids double-scanning projects that appear in both groups and membership lists
- Prints the groups and projects that are being analyzed
- Prints the contributor count for individual groups and standalone projects
- Prints the consolidated deduplicated report with name of each GitLab user, along with a link to a commit they've made in the last 90 days

### Running the script:

- Create a venv with `python3 -m venv .venv` in the directory titled `Gitlab`, and activate with `source .venv/bin/activate`
- Install dependencies with `pip3 install -r requirements.txt`
- Set your GitLab token: `export GITLAB_TOKEN=your_token_here`
- Run with the command `python3 gitlab_contributor_count.py`

### Options:

- `--url` / `-u`: GitLab instance URL (default: `https://gitlab.com`). Use this for self-hosted instances.
- `--token` / `-t`: GitLab Personal Access Token (overrides `GITLAB_TOKEN` env var)
- `--days` / `-d`: Number of days to look back (default: 90)
- `--exclude-bots`: Exclude bot/service accounts from the contributor count
- `--verbose` / `-v`: Print API diagnostics to stderr
- `--list-contributors`: List individual contributors and their emails
- `--format`: Output format (`text`, `json`, or `markdown`)

Note: The token used as `GITLAB_TOKEN` should have `read_api` and `read_user` access.

## Bitbucket

### Bitbucket Cloud

- Counts the number of unique contributing developers within a configurable time window (default: 90 days) of a given Bitbucket Workspace
- Supports text and JSON output formats
- Requires an App Password with `Repositories: Read` permission

#### Running the script:

- Create a venv with `python3 -m venv .venv` in the directory titled `bitbucket`, and activate with `source .venv/bin/activate`
- Install dependencies with `pip3 install -r requirements.txt`
- Set your credentials: `export BITBUCKET_USER=your_username` and `export BITBUCKET_PASSWORD=your_app_password`
- Run with the command `python3 bitbucket_contributors_90d.py --workspace <workspace-slug>`

#### Options:

- `--workspace` / `-w`: Bitbucket Workspace ID/Slug (required)
- `--user` / `-u`: Bitbucket username (overrides `BITBUCKET_USER` env var)
- `--password` / `-p`: Bitbucket App Password (overrides `BITBUCKET_PASSWORD` env var)
- `--days` / `-d`: Number of days to look back (default: 90)
- `--exclude-bots`: Exclude bot/service accounts from the contributor count
- `--verbose` / `-v`: Print API diagnostics to stderr
- `--list-contributors`: List individual contributors and their emails
- `--format`: Output format (`text`, `json`, or `markdown`)

### Bitbucket Server / Data Center

- Counts the number of unique contributing developers within a configurable time window (default: 90 days) of a given Bitbucket Server Project
- Uses the Bitbucket Server REST API (1.0)
- Automatically stops paginating commits once it reaches the 90-day boundary

#### Running the script:

- Set your credentials: `export BITBUCKET_USER=your_username` and `export BITBUCKET_PASSWORD=your_password`
- Run with the command `python3 bitbucket_server_contributors_90d.py --project <PROJECT_KEY> --url https://bitbucket.mycompany.com`

#### Options:

- `--project` / `-p`: Bitbucket Project Key (required)
- `--url`: Bitbucket Server Base URL (required)
- `--user` / `-u`: Username (overrides `BITBUCKET_USER` env var)
- `--password` / `-pw`: Password/Token (overrides `BITBUCKET_PASSWORD` env var)
- `--days` / `-d`: Number of days to look back (default: 90)
- `--exclude-bots`: Exclude bot/service accounts from the contributor count
- `--verbose` / `-v`: Print API diagnostics to stderr
- `--list-contributors`: List individual contributors and their emails
- `--format`: Output format (`text`, `json`, or `markdown`)

## Azure DevOps

- Counts the number of unique contributing developers within a configurable time window (default: 90 days) of a given Azure DevOps Project
- Scans all Git repositories within the project
- Handles pagination via continuation tokens for large organizations
- Requires a Personal Access Token (PAT) with `Code (Read)` scope

### Running the script:

- Create a venv with `python3 -m venv .venv` in the directory titled `azure_devops`, and activate with `source .venv/bin/activate`
- Install dependencies with `pip3 install -r requirements.txt`
- Set your token: `export ADO_TOKEN=your_pat_here`
- Run with the command `python3 ado_contributors_90d.py --org https://dev.azure.com/myorg --project <project-name>`

### Options:

- `--org` / `-o`: Azure DevOps Org URL (required, e.g. `https://dev.azure.com/myorg`)
- `--project` / `-p`: Project name (required)
- `--token` / `-t`: Personal Access Token (overrides `ADO_TOKEN` env var)
- `--days` / `-d`: Number of days to look back (default: 90)
- `--exclude-bots`: Exclude bot/service accounts from the contributor count
- `--verbose` / `-v`: Print API diagnostics to stderr
- `--list-contributors`: List individual contributors and their emails
- `--format`: Output format (`text`, `json`, or `markdown`)

</details>

## Running Tests

From the project root:

```bash
pip install -r requirements-test.txt
pytest tests/ -v
```

## No Warranty

Please be advised that this software is provided on an "as is" basis, without warranty of any kind, express or implied. The authors and contributors make no representations or warranties of any kind concerning the safety, suitability, lack of viruses, inaccuracies, typographical errors, or other harmful components of this software. There are inherent dangers in the use of any software, and you are solely responsible for determining whether this software is compatible with your equipment and other software installed on your equipment.

By using this software, you acknowledge that you have read this disclaimer, understand it, and agree to be bound by its terms and conditions. You also agree that the authors and contributors of this software are not liable for any damages you may suffer as a result of using, modifying, or distributing this software.