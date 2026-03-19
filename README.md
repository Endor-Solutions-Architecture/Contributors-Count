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

```bash
# Clone the repo
git clone https://github.com/Endor-Solutions-Architecture/Contributors-Count.git
cd Contributors-Count

# Pick your platform directory and set up a virtualenv
cd GitHub
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Set your token and run
export GITHUB_TOKEN=your_token_here
python3 github_contributors_90d.py --org my-org
```

That's it. You'll see output like this:

```
Fetching repositories for my-org ...
  Found 42 repositories.

  [ 1/42] api-gateway ... 156 commits
  [ 2/42] web-frontend ... 312 commits
  ...
  [42/42] docs-site ... 23 commits

========================================
Organization: my-org
Scan Date: 2026-03-19
Repositories scanned: 42
Bots excluded: No
----------------------------------------
Contributors in last 90 days: 67
========================================
```

## Supported Platforms

| Platform | Script | Auth |
|----------|--------|------|
| **GitHub** (Cloud & Enterprise) | `GitHub/github_contributors_90d.py` | PAT via `GITHUB_TOKEN` |
| **GitLab** (Cloud & Self-Hosted) | `Gitlab/gitlab_contributor_count.py` | PAT via `GITLAB_TOKEN` |
| **Bitbucket Cloud** | `bitbucket/bitbucket_contributors_90d.py` | App Password via `BITBUCKET_USER` + `BITBUCKET_PASSWORD` |
| **Bitbucket Server / Data Center** | `bitbucket/bitbucket_server_contributors_90d.py` | Username/Password via `BITBUCKET_USER` + `BITBUCKET_PASSWORD` |
| **Azure DevOps** | `azure_devops/ado_contributors_90d.py` | PAT via `ADO_TOKEN` |

## Common Options

Every script supports the same core flags:

| Flag | Description |
|------|-------------|
| `--days` / `-d` | Time window in days (default: **90**) |
| `--exclude-bots` | Filter out bot and service accounts |
| `--verbose` / `-v` | Print API diagnostics to stderr |
| `--list-contributors` | Show each contributor and their email(s) |
| `--format` | Output as `text` (default), `json`, or `markdown` |

## Output Formats

### Text (default)

Human-readable summary printed to stdout. Progress is shown as repos are scanned.

### JSON

Machine-readable output for piping into other tools:

```bash
python3 github_contributors_90d.py --org my-org --format json
```

```json
{
  "org": "my-org",
  "scan_date": "2026-03-19",
  "days": 90,
  "default_branch_only": false,
  "exclude_bots": false,
  "unique_contributors": 67,
  "repositories_scanned": 42,
  "skipped_repos": []
}
```

### Markdown

A shareable report with summary table and collapsible per-repo breakdown:

```bash
python3 github_contributors_90d.py --org my-org --format markdown > report.md
```

```markdown
# Contributors Report — GitHub

| Field | Value |
|-------|-------|
| **Organization** | my-org |
| **Scan Date** | 2026-03-19 |
| **Time Window** | 90 days |
| **Repositories Scanned** | 42 |
| **Bots Excluded** | No |
| **Scan Duration** | 2m 14s |

## Unique Contributors: 67

<details>
<summary>Per-Repository Breakdown</summary>

| Repository | Commits |
|------------|---------|
| web-frontend | 312 |
| api-gateway | 156 |
| ... | ... |

</details>
```

## Common Recipes

```bash
# Last 30 days, exclude bots, with contributor list
python3 github_contributors_90d.py --org my-org --days 30 --exclude-bots --list-contributors

# Generate a markdown report for last quarter
python3 github_contributors_90d.py --org my-org --days 90 --format markdown > Q1-contributors.md

# Quick test run on a large org (limit to 5 repos)
python3 github_contributors_90d.py --org my-org --max-repos 5

# GitLab self-hosted instance
python3 gitlab_contributor_count.py --url https://gitlab.mycompany.com --days 60

# Debug API issues with verbose mode
python3 ado_contributors_90d.py --org https://dev.azure.com/myorg --project myproj --verbose 2>debug.log
```

---

<details>
<summary><strong>Platform-Specific Setup & Options</strong></summary>

## GitHub

### Setup

```bash
cd GitHub
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GITHUB_TOKEN=your_token_here
```

### Token Permissions

**Fine-grained tokens (recommended):**
- Repository Permissions: `Metadata: Read-only`, `Contents: Read-only`
- Organization Permissions: `Members: Read-only`

**Classic tokens:** `repo` scope (for private repos) or no scopes (for public orgs, with higher rate limits).

### Options

| Flag | Description |
|------|-------------|
| `--org` / `-o` | GitHub organization name **(required)** |
| `--token` / `-t` | PAT (overrides `GITHUB_TOKEN` env var) |
| `--base-url` | GitHub API base URL (for GitHub Enterprise Server) |
| `--default-branch-only` | Only count commits from each repo's default branch |
| `--exclude-bots` | Exclude bot accounts (GitHub `type: "Bot"` + `[bot]` suffix) |
| `--max-repos` | Limit number of repositories (useful for testing) |
| `--days` / `-d` | Days to look back (default: 90) |
| `--verbose` / `-v` | API diagnostics on stderr |
| `--list-contributors` | Show contributor details |
| `--format` | `text`, `json`, or `markdown` |

### Notes

- Scans **all branches** by default to capture feature-branch contributors
- Uses 4 concurrent workers for faster scanning on large orgs
- Supports GitHub Enterprise Server via `--base-url https://github.mycompany.com/api/v3`

---

## GitLab

### Setup

```bash
cd Gitlab
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GITLAB_TOKEN=your_token_here
```

### Token Permissions

The token needs `read_api` and `read_user` scopes.

### Options

| Flag | Description |
|------|-------------|
| `--url` / `-u` | GitLab instance URL (default: `https://gitlab.com`) |
| `--token` / `-t` | PAT (overrides `GITLAB_TOKEN` env var) |
| `--exclude-bots` | Exclude bot/service accounts |
| `--days` / `-d` | Days to look back (default: 90) |
| `--verbose` / `-v` | API diagnostics on stderr |
| `--list-contributors` | Show contributor details |
| `--format` | `text`, `json`, or `markdown` |

### Notes

- Scans all accessible groups and standalone projects
- Deduplicates across groups to avoid double-counting
- Avoids re-scanning projects that appear in multiple groups

---

## Bitbucket Cloud

### Setup

```bash
cd bitbucket
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export BITBUCKET_USER=your_username
export BITBUCKET_PASSWORD=your_app_password
```

### Token Permissions

Create an **App Password** with `Repositories: Read` permission.

### Options

| Flag | Description |
|------|-------------|
| `--workspace` / `-w` | Workspace ID/slug **(required)** |
| `--user` / `-u` | Username (overrides `BITBUCKET_USER`) |
| `--password` / `-p` | App Password (overrides `BITBUCKET_PASSWORD`) |
| `--exclude-bots` | Exclude bot/service accounts |
| `--days` / `-d` | Days to look back (default: 90) |
| `--verbose` / `-v` | API diagnostics on stderr |
| `--list-contributors` | Show contributor details |
| `--format` | `text`, `json`, or `markdown` |

---

## Bitbucket Server / Data Center

### Setup

```bash
export BITBUCKET_USER=your_username
export BITBUCKET_PASSWORD=your_password
```

### Options

| Flag | Description |
|------|-------------|
| `--project` / `-p` | Project Key **(required)** |
| `--url` | Bitbucket Server base URL **(required)** |
| `--user` / `-u` | Username (overrides `BITBUCKET_USER`) |
| `--password` / `-pw` | Password/token (overrides `BITBUCKET_PASSWORD`) |
| `--exclude-bots` | Exclude bot/service accounts |
| `--days` / `-d` | Days to look back (default: 90) |
| `--verbose` / `-v` | API diagnostics on stderr |
| `--list-contributors` | Show contributor details |
| `--format` | `text`, `json`, or `markdown` |

### Notes

- Uses the Bitbucket Server REST API (1.0)
- Stops paginating commits once it reaches the time window boundary

---

## Azure DevOps

### Setup

```bash
cd azure_devops
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ADO_TOKEN=your_pat_here
```

### Token Permissions

Create a PAT with `Code (Read)` scope.

### Options

| Flag | Description |
|------|-------------|
| `--org` / `-o` | Organization URL **(required)**, e.g. `https://dev.azure.com/myorg` |
| `--project` / `-p` | Project name **(required)** |
| `--token` / `-t` | PAT (overrides `ADO_TOKEN`) |
| `--exclude-bots` | Exclude bot/service accounts |
| `--days` / `-d` | Days to look back (default: 90) |
| `--verbose` / `-v` | API diagnostics on stderr |
| `--list-contributors` | Show contributor details |
| `--format` | `text`, `json`, or `markdown` |

### Notes

- Scans all Git repositories within the project
- Handles pagination via continuation tokens

</details>

## Running Tests

```bash
pip install -r requirements-test.txt
pytest tests/ -v
```

The test suite covers CLI argument validation, contributor deduplication, bot exclusion, verbose mode, and all output formats across every platform. See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup details.

## FAQ

**Does this count merged code only, or all branches?**
By default, scripts scan all branches to capture contributors on feature branches. On GitHub, use `--default-branch-only` to restrict to the default branch. Other platforms scan all branches.

**How does deduplication work?**
Each platform uses the strongest available identity: GitHub uses login handles, GitLab and Azure DevOps use email addresses, and Bitbucket uses `account_id` (Cloud) or email (Server). When a developer commits with multiple emails, they may be counted more than once — this is a known trade-off since there's no universal identity across these platforms. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for details.

**What counts as a "bot"?**
The `--exclude-bots` flag uses heuristic detection: accounts ending in `[bot]`, known service names (dependabot, renovate, snyk, mergify, etc.), and bot-like email patterns (noreply, pipeline@). On GitHub, the API's `type: "Bot"` field is also checked.

**Why are some repos skipped?**
Repos can be skipped due to permission errors, empty repositories, or API timeouts. Skipped repos are reported in all output formats. Use `--verbose` for detailed diagnostics.

**Can I use this in CI/CD?**
Yes. Use `--format json` for machine-readable output and set tokens via environment variables. The exit code is 0 on success and non-zero on fatal errors.

**What's the API rate limit impact?**
Each script makes one API call per page of repositories and one per page of commits per repo. GitHub uses 4 concurrent workers. All scripts handle rate limiting automatically (429 responses trigger a wait-and-retry). Use `--verbose` to see rate limit events.

**Is there a single unified CLI?**
Not currently — each platform has its own script with platform-specific authentication. This keeps dependencies minimal and each script self-contained.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, code style, and how to add support for a new platform.

## No Warranty

This software is provided "as is", without warranty of any kind, express or implied. The authors and contributors make no representations or warranties concerning the safety, suitability, or correctness of this software. You are solely responsible for determining whether it is compatible with your environment. By using this software, you acknowledge and agree that the authors are not liable for any damages arising from its use, modification, or distribution.
