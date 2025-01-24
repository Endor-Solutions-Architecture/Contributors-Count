# Git Contributor Counter

A tool for counting and analyzing contributors across GitHub and GitLab organizations. 

## Features

- Support for GitHub and GitLab (including self-hosted instances)
- Repository inclusion/exclusion patterns
- Flexible contributor filtering (bots, service accounts, specific users)
- Contributor level 

## Installation

```bash
# Clone the repository
git clone https://github.com/Endor-Solutions-Architecture/Contributors-Count.git
cd Contributors-Count

# Create a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip3 install -r requirements.txt
```

## Configuration

Set up a configuration file to pass to the script. At a minimum, you must specify your Git SCM provider details

```yaml
# config.yml
provider:
  type: github  # or gitlab
  org: your-organization
  url: https://api.github.com  # optional, for self-hosted instances

repositories:
  include:
    - pattern: "*"            # include all repositories
  
  exclude:
    - pattern: "*-test"       # exclude repositories ending in -test
    - pattern: "temp-*"       # exclude temporary repositories
    - exact: "excluded-repo"

contributors:
  exclude:
    - pattern: "*bot"    # GitHub-style bot accounts
    - users:
        - "dependabot"
        - "renovate"
    - emails:
        - "*-bot@*"
        - "noreply@github.com"
```

## Token Configuration

### GitHub

Create a Fine-Grained Personal Access Token:
1. Go to GitHub Settings → Developer Settings → Personal Access Tokens → Fine-grained tokens
2. Click "Generate new token"
3. Required Permissions:
   - Repository permissions:
     - Contents: Read-only
     - Metadata: Read-only
   - Organization permissions:
     - Members: Read-only

### GitLab

Create a Personal Access Token:
1. Go to GitLab Settings → Access Tokens
2. Create a new token with the following scopes:
   - `read_api`
   - `read_user`
   - `read_repository`

For self-hosted GitLab instances, ensure the token has appropriate group/project access.

## Usage
Run the contributer_count module passing arguments for:
- Your [config.yml file](#configuration)
- Your appropriately permissioned token ([Token Configuration](#token-configuration))

```bash
# Count contributors for the organization defined in configuration file
python3 -m contributer_count --config config.yml --token your-token

# Count contributors for the organization defined in configuration file, generate output.json file explaining analysis
python3 -m contributer_count --config config.yml --token your-token --explain
```

## Script Output

### output.json
Passing `--explain` tells the script to generate a file, `output.json` summarizing the repos and contributors that make up the total numbers.

```json
{
  "metadata": {
    "organization": "your-org",
    "provider": "github",
    "period": {
      "start": "2024-01-01T00:00:00Z",
      "end": "2024-03-31T23:59:59Z"
    }
  },
  "summary": {
    "total_contributors": 42,
    "total_repositories": 15,
    "total_commits": 1337
  },
  "contributors": {
    "username": {
      "email": "user@example.com",
      "commit_count": 50,
      "repositories": ["repo1", "repo2"]
    }
  },
  "repositories": {
    "repo1": {
      "contributor_count": 5,
      "commit_count": 100,
      "contributors": ["user1", "user2"]
    }
  }
}
```

## No Warranty

Please be advised that this software is provided on an "as is" basis, without warranty of any kind, express or implied. The authors and contributors make no representations or warranties of any kind concerning the safety, suitability, lack of viruses, inaccuracies, typographical errors, or other harmful components of this software. There are inherent dangers in the use of any software, and you are solely responsible for determining whether this software is compatible with your equipment and other software installed on your equipment.

By using this software, you acknowledge that you have read this disclaimer, understand it, and agree to be bound by its terms and conditions. You also agree that the authors and contributors of this software are not liable for any damages you may suffer as a result of using, modifying, or distributing this software.
