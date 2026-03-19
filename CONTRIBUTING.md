# Contributing to Contributors-Count

Thank you for your interest in contributing. This guide covers everything you need to get started.

## Development Setup

```bash
git clone https://github.com/Endor-Solutions-Architecture/Contributors-Count.git
cd Contributors-Count

python3 -m venv .venv
source .venv/bin/activate

# Install all dependencies (all platforms + tests)
pip install -r requirements-test.txt
pip install -r GitHub/requirements.txt
pip install -r Gitlab/requirements.txt
pip install -r bitbucket/requirements.txt
pip install -r azure_devops/requirements.txt

# Run the tests
pytest tests/ -v
```

## Project Structure

```
Contributors-Count/
├── contributors_count.py             # Unified cross-platform runner
├── platforms.json.example            # Config template for unified mode
├── GitHub/
│   └── github_contributors_90d.py
├── Gitlab/
│   └── gitlab_contributor_count.py
├── bitbucket/
│   ├── bitbucket_contributors_90d.py
│   └── bitbucket_server_contributors_90d.py
├── azure_devops/
│   └── ado_contributors_90d.py
├── tests/
│   ├── conftest.py
│   ├── test_github.py
│   ├── test_gitlab.py
│   ├── test_bitbucket_cloud.py
│   ├── test_bitbucket_server.py
│   ├── test_ado.py
│   └── test_unified.py
├── docs/
│   ├── ARCHITECTURE.md
│   └── CHANGELOG.md
├── CONTRIBUTING.md
└── README.md
```

## Running Tests

```bash
pytest tests/ -v                          # All tests
pytest tests/test_github.py -v            # One platform
pytest tests/test_unified.py -v           # Unified runner
pytest tests/test_ado.py::TestBotExclusion -v  # One test class
```

## Code Style

- **Python 3.6+** compatibility
- **Click** for CLI parsing
- Private helpers prefixed with `_`
- Constants in `UPPER_SNAKE_CASE`
- Output to stdout, diagnostics/warnings to stderr

## Adding a New Platform

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the script structure pattern. Each new platform needs:

1. A directory with the script and `requirements.txt`
2. Standard CLI options (`--days`, `--exclude-bots`, `--verbose`, `--format`, `--list-contributors`)
3. The `_is_bot()` helper with platform-appropriate heuristics
4. Three output formats (text, json, markdown)
5. Tests in `tests/test_<platform>.py`
6. A scanner function in `contributors_count.py` for unified mode integration
7. Updated README

## Submitting Changes

1. Create a feature branch from `main`
2. Make your changes with tests
3. Run `pytest tests/ -v` and ensure all tests pass
4. Open a pull request with a clear description

## Reporting Bugs

Include: platform, exact command (with `--verbose`), error output, and Python version.
