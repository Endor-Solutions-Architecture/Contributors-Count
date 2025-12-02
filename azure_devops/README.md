# Azure DevOps Contributors 90-Day Count

A CLI tool to calculate the number of unique contributing developers in an Azure DevOps Project over the last 90 days.

## Features

- **90-Day Count**: Calculates unique contributors (by email) for the last 90 days.
- **Project-Wide**: Scans all Git repositories within a project.
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

You need a **Personal Access Token (PAT)** with **Code (Read)** scope.

### Basic Usage

1.  **Set the token as an environment variable:**

    ```bash
    export ADO_TOKEN=your_pat_here
    ```

2.  **Run the script:**

    ```bash
    python ado_contributors_90d.py --org https://dev.azure.com/myorg --project myproject
    ```

### JSON Output

```bash
python ado_contributors_90d.py --org https://dev.azure.com/myorg --project myproject --format json
```

**Output:**
```json
{
  "org": "https://dev.azure.com/myorg",
  "project": "myproject",
  "scan_date": "2025-12-02",
  "contributors_90d": 8
}
```
