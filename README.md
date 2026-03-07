# Contributing Developers Count

A collection of CLI tools that count unique contributing developers over the last 90 days across GitHub, GitLab, Bitbucket, and Azure DevOps. All tools feature automatic retry with exponential backoff, connection timeouts, rate-limit handling, and clean summary output suitable for customer-facing sizing exercises.

**Requirements:** Python 3.6+

## GitHub

- Counts the number of contributing developers within the last 90 days of a given GitHub Organization
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
- `--base-url`: GitHub API base URL, for GitHub Enterprise Server (default: `https://api.github.com`)
- `--default-branch-only`: Only count commits from each repository's default branch
- `--exclude-bots`: Exclude bot accounts from the contributor count
- `--list-contributors`: List individual contributors and their emails
- `--format`: Output format (`text` or `json`)
- `--max-repos`: Limit number of repositories to process (useful for testing)

## GitLab

- Counts the number of contributing developers within the last 90 days across all accessible GitLab groups and projects
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
- `--list-contributors`: List individual contributors and their emails
- `--format`: Output format (`text` or `json`)

Note: The token used as `GITLAB_TOKEN` should have `read_api` and `read_user` access.

## Bitbucket

### Bitbucket Cloud

- Counts the number of unique contributing developers within the last 90 days of a given Bitbucket Workspace
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
- `--list-contributors`: List individual contributors and their emails
- `--format`: Output format (`text` or `json`)

### Bitbucket Server / Data Center

- Counts the number of unique contributing developers within the last 90 days of a given Bitbucket Server Project
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
- `--list-contributors`: List individual contributors and their emails
- `--format`: Output format (`text` or `json`)

## Azure DevOps

- Counts the number of unique contributing developers within the last 90 days of a given Azure DevOps Project
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
- `--list-contributors`: List individual contributors and their emails
- `--format`: Output format (`text` or `json`)

## No Warranty

Please be advised that this software is provided on an "as is" basis, without warranty of any kind, express or implied. The authors and contributors make no representations or warranties of any kind concerning the safety, suitability, lack of viruses, inaccuracies, typographical errors, or other harmful components of this software. There are inherent dangers in the use of any software, and you are solely responsible for determining whether this software is compatible with your equipment and other software installed on your equipment.

By using this software, you acknowledge that you have read this disclaimer, understand it, and agree to be bound by its terms and conditions. You also agree that the authors and contributors of this software are not liable for any damages you may suffer as a result of using, modifying, or distributing this software.