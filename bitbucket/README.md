# Bitbucket Contributors 90-Day Count

A CLI tool to calculate the number of unique contributing developers in a Bitbucket Workspace over the last 90 days.

## Features

- **90-Day Count**: Calculates unique contributors for the last 90 days.
- **Workspace-Wide**: Scans all repositories within a workspace.
- **Detailed Listing**: Optionally lists contributor emails.
- **Output Formats**: Human-readable text or JSON.

## Requirements

- Python 3.6+
- Dependencies: `requests`, `click`

## Installation

1.  Install dependencies:

    ```bash
    pip install -r requirements.txt
    ```

## Usage

### Prerequisites

You need an **App Password** with **Repositories: Read** permission.

### Basic Usage

1.  **Set credentials as environment variables:**

    ```bash
    export BITBUCKET_USER=your_username
    export BITBUCKET_PASSWORD=your_app_password
    ```

2.  **Run the script:**

    ```bash
    python bitbucket_contributors_90d.py --workspace my-workspace
    ```

### JSON Output

```bash
python bitbucket_contributors_90d.py --workspace my-workspace --format json
```

**Output:**
```json
{
  "workspace": "my-workspace",
  "scan_date": "2025-12-02",
  "contributors_90d": 5
}
```

## Bitbucket Server (Data Center)

For self-hosted Bitbucket Server / Data Center instances, use the `bitbucket_server_contributors_90d.py` script.

### Usage

1.  **Set credentials and URL:**

    ```bash
    export BITBUCKET_SERVER_URL=https://bitbucket.mycompany.com
    export BITBUCKET_USER=myuser
    export BITBUCKET_PASSWORD=mypassword
    ```

2.  **Run the script:**

    ```bash
    python bitbucket_server_contributors_90d.py --project MYPROJ --url https://bitbucket.mycompany.com
    ```




