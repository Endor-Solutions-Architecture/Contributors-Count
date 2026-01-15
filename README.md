# Contributing Developers Count

## Github

- Counts the number of contributing developers within the last 90 days of a given GitHub Organization
- Scans all branches by default to capture contributors on feature branches (not just merged code)
- Supports filtering to only count commits from each repository's default branch with `--default-branch-only`
- Prints the name of each GitHub user along with their email addresses
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
- `--default-branch-only`: Only count commits from each repository's default branch
- `--list-contributors`: List individual contributors and their emails
- `--format`: Output format (`text` or `json`)
- `--max-repos`: Limit number of repositories to process

## Gitlab

- Counts the number of contributing developers within the last 90 days of a given Gitlab Organization
- Prints the groups and projects that are being analyzed
- Prints the contributor count for individual groups and orphan projects(Projects without groups) too.
- Prints the consolidated deduplicated report with name of each Gitlab user, along with a link to a commit they've given in the last 90 days

### Running the script:

- Create a venv with `python3 -m venv .venv` in the directory titled `Gitlab`, and activate with `source .venv/bin/activate`
- Install dependencies with `pip3 install -r requirements.txt`
- Edit the org name for the variable called `GITLAB_URL` to the Gitlab host incase you are using self hosted Gitlab instance
- Run with the command `python3 gitlab_contributor_count.py`

Note: The token used as GITLAB_TOKEN should have read_api and read_user access


_Support for other SCM providers coming soon!_

## No Warranty

Please be advised that this software is provided on an "as is" basis, without warranty of any kind, express or implied. The authors and contributors make no representations or warranties of any kind concerning the safety, suitability, lack of viruses, inaccuracies, typographical errors, or other harmful components of this software. There are inherent dangers in the use of any software, and you are solely responsible for determining whether this software is compatible with your equipment and other software installed on your equipment.

By using this software, you acknowledge that you have read this disclaimer, understand it, and agree to be bound by its terms and conditions. You also agree that the authors and contributors of this software are not liable for any damages you may suffer as a result of using, modifying, or distributing this software.