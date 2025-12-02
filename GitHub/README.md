# GitHub Contributors in the last 90 days

A CLI tool to calculate the number of unique contributing developers in a GitHub organization over the last 90 days.

## Features

- **90-Day Count**: Calculates unique contributors for the last 90 days.
- **Detailed Listing**: Optionally lists contributor handles and emails.
- **Output Formats**: Human-readable text or JSON for automation.
- **Secure**: Supports Personal Access Tokens (PAT) for private organizations.

## Requirements

- Python 3.6+
- Dependencies: `requests`, `click`

## Installation

1.  Clone this repository or download the script.
2.  Install dependencies:

    ```bash
    pip install -r requirements.txt
    ```

## Usage

### Basic Usage (Public Organizations)

For public organizations, you can run the script without a token (subject to lower API rate limits).

```bash
python github_contributors_90d.py --org <org-name>
```

Example:
```bash
python github_contributors_90d.py --org google
```

### Private Organizations (or higher rate limits)

For private organizations, or to avoid rate limits on public orgs, use a GitHub Personal Access Token (PAT).

1.  **Set the token as an environment variable (Recommended):**

    ```bash
    export GITHUB_TOKEN=your_token_here
    # On Windows PowerShell:
    # $env:GITHUB_TOKEN="your_token_here"
    ```

2.  **Run the script:**

    ```bash
    python github_contributors_90d.py --org <org-name>
    ```

Alternatively, pass the token via the `--token` flag:
```bash
python github_contributors_90d.py --org <org-name> --token your_token_here
```

### Detailed Contributor List

To see the list of individual contributors and their emails:

```bash
python github_contributors_90d.py --org google --list-contributors
```

### JSON Output

For integration with other tools, use the JSON format:

```bash
python github_contributors_90d.py --org google --format json
```

**Output:**
```json
{
  "org": "google",
  "scan_date": "2025-12-02",
  "contributors_90d": 450
}
```



## Permissions & Scopes

The required permissions for your Personal Access Token (PAT) depend on the organization type:

### Public Organizations
- **No scopes required.** A token with no scopes selected is sufficient to increase your rate limit.

### Private Organizations
You need a **Classic PAT** with the following scopes:
- **`read:org`**: To list the organization's repositories.
- **`repo`**: To read commits from private repositories.

**Fine-grained PATs:**
If using a Fine-grained token, you do not select "scopes". Instead, select the organization and grant these specific permissions:
1.  **Repository access**: Select "All repositories" (or the specific ones you want to count).
2.  **Repository permissions**:
    - **`Contents`**: **Read-only** (to fetch commits).
    - **`Metadata`**: **Read-only** (to list repositories).
3.  **Organization permissions**:
    - None strictly required for this script if you have Repository access, but **`Members` (Read-only)** is good practice if you run into visibility issues.

## Help

View all available options:

```bash
python github_contributors_90d.py --help
```

