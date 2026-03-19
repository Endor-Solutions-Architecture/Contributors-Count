# Contributing to Contributors-Count

Thank you for your interest in contributing. This guide covers everything you need to get started.

## Development Setup

1. **Clone the repo:**

   ```bash
   git clone https://github.com/Endor-Solutions-Architecture/Contributors-Count.git
   cd Contributors-Count
   ```

2. **Create a virtualenv** (from the project root):

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install all dependencies** (covers every platform + test tooling):

   ```bash
   pip install -r requirements-test.txt
   pip install -r GitHub/requirements.txt
   pip install -r Gitlab/requirements.txt
   pip install -r bitbucket/requirements.txt
   pip install -r azure_devops/requirements.txt
   ```

4. **Run the tests:**

   ```bash
   pytest tests/ -v
   ```

## Project Structure

```
Contributors-Count/
├── GitHub/
│   ├── github_contributors_90d.py    # GitHub scanner
│   └── requirements.txt
├── Gitlab/
│   ├── gitlab_contributor_count.py   # GitLab scanner
│   └── requirements.txt
├── bitbucket/
│   ├── bitbucket_contributors_90d.py         # Bitbucket Cloud scanner
│   ├── bitbucket_server_contributors_90d.py  # Bitbucket Server scanner
│   └── requirements.txt
├── azure_devops/
│   ├── ado_contributors_90d.py       # Azure DevOps scanner
│   └── requirements.txt
├── tests/
│   ├── conftest.py                   # Python path setup for imports
│   ├── test_github.py
│   ├── test_gitlab.py
│   ├── test_bitbucket_cloud.py
│   ├── test_bitbucket_server.py
│   └── test_ado.py
├── docs/
│   ├── ARCHITECTURE.md               # System design and patterns
│   └── CHANGELOG.md                  # Version history
├── README.md
├── CONTRIBUTING.md                   # This file
└── requirements-test.txt             # Test dependencies
```

Each platform directory is self-contained with its own `requirements.txt`. The `tests/conftest.py` adds all platform directories to `sys.path` so tests can import from any script.

## Running Tests

The test suite uses `pytest` with `unittest.mock` to simulate API responses — no actual network calls are made.

```bash
# Run all tests
pytest tests/ -v

# Run tests for a specific platform
pytest tests/test_github.py -v

# Run a single test class
pytest tests/test_ado.py::TestBotExclusion -v
```

Every PR should have passing tests. If you add a feature, add corresponding tests.

## Code Style

- **Python 3.6+** compatibility (type hints use `typing` module, not `X | Y` syntax)
- **Click** for CLI argument parsing — all scripts use the same pattern
- **Private helpers** are prefixed with `_` (e.g., `_fetch_commits`, `_is_bot`)
- **Public functions** are kept to a minimum: `fetch_repos` and the `main` Click command
- **Constants** are `UPPER_SNAKE_CASE` at module level
- **Error handling**: API errors raise `ApiError`; per-repo failures are caught and logged, never fatal
- **Output goes to stdout**, diagnostics and warnings go to **stderr**

## Adding a New Platform

Each script follows a consistent architecture. To add support for a new platform:

1. **Create a new directory** (e.g., `gerrit/`) with a `requirements.txt`.

2. **Write the script** following the established pattern:

   ```
   Module docstring with usage examples
   ─────────────────────────────
   Imports
   Constants (env var names, timeouts, API versions)
   ─────────────────────────────
   Helpers (_sanitize, _elapsed, _summary_box)
   Bot detection (_is_bot)
   ─────────────────────────────
   Exceptions (ApiError)
   Client class (with retry, rate-limit handling)
   Data fetching (fetch_repos, _fetch_commits)
   ─────────────────────────────
   CLI (@click.command with standard options)
   main() function
   ```

3. **Implement these standard CLI options:**
   - Platform-specific auth (token, user/password)
   - `--days` / `-d` (default: 90)
   - `--exclude-bots`
   - `--verbose` / `-v`
   - `--list-contributors`
   - `--format` (`text`, `json`, `markdown`)

4. **Implement the `_is_bot()` helper** with platform-appropriate heuristics.

5. **Add three output formats:**
   - **text**: Progress during scan, summary box at the end
   - **json**: Structured payload with `unique_contributors`, `days`, `scan_date`, `exclude_bots`, `skipped_repos`
   - **markdown**: Report with summary table, contributor table, collapsible per-repo breakdown

6. **Write tests** in `tests/test_<platform>.py` covering:
   - CLI argument validation (required args, `--help`, invalid `--days`)
   - Client construction (auth headers, URL handling)
   - Contributor deduplication
   - Bot exclusion
   - Verbose mode
   - All output formats

7. **Update the root README.md** with setup instructions and options table.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the detailed design patterns.

## Submitting Changes

1. Create a feature branch from `main`.
2. Make your changes with tests.
3. Run `pytest tests/ -v` and ensure all tests pass.
4. Open a pull request with a clear description of what changed and why.

## Reporting Bugs

When filing an issue, include:

- The platform and script you were using
- The exact command you ran
- The error output (run with `--verbose` for extra detail: `python3 <script> ... --verbose 2>&1`)
- Your Python version (`python3 --version`)
