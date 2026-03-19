# Architecture

This document describes the design patterns and decisions behind Contributors-Count.

## Overview

Contributors-Count is a collection of standalone Python CLI tools, one per platform. Each script is fully self-contained — it can be copied to any machine with Python 3.6+ and its dependencies, without needing the rest of the repository.

```
User
 │
 ▼
┌──────────────────────────────┐
│  CLI (Click)                 │  Parses flags, validates input, sets up auth
│  main()                      │
├──────────────────────────────┤
│  API Client                  │  HTTP session with retry, rate-limit handling
│  ADOClient / BitbucketClient │
├──────────────────────────────┤
│  Data Fetching               │  fetch_repos → _fetch_commits (paginated)
│  Generators for lazy paging  │
├──────────────────────────────┤
│  Processing                  │  Deduplication, bot filtering, counting
├──────────────────────────────┤
│  Output                      │  text / json / markdown rendering
└──────────────────────────────┘
```

## Script Structure

Every script follows the same layout:

```
1. Module docstring           Usage examples, requirements, token scopes
2. Imports                    stdlib → third-party → (no local imports)
3. Constants                  Env var names, timeouts, API versions
4. Helpers                    _sanitize(), _elapsed(), _summary_box()
5. Bot detection              _is_bot() with platform-tuned heuristics
6. Exceptions                 ApiError(status_code, message)
7. Client class               Session setup, retry strategy, _get(), pagination
8. Data fetching              fetch_repos(), _fetch_commits()
9. CLI definition             @click.command with options
10. main() function           Orchestrates fetch → process → output
```

This consistent structure means you can navigate any script if you know one.

## API Client Pattern

Each platform has a client class that encapsulates:

- **Session setup**: `requests.Session` with auth headers, User-Agent, connection pooling
- **Retry strategy**: `urllib3.util.retry.Retry` with exponential backoff on 5xx errors
- **Rate limit handling**: 429 responses trigger a wait based on `Retry-After` header
- **Pagination**: Platform-specific (GitHub uses `Link` headers, ADO uses continuation tokens, Bitbucket uses `next` URLs, GitLab uses `python-gitlab`'s built-in pagination)

```python
class PlatformClient:
    def __init__(self, token, base_url):
        self._session = requests.Session()
        # Auth, retry adapter, connection pooling
    
    def _get(self, url, params=None):
        # Core request with rate-limit loop
    
    def get_paginated(self, url, ...):
        # Yields items across all pages
```

The `_get` method is the single point where all HTTP requests flow through, making it easy to add logging, metrics, or caching.

## Deduplication Strategy

Each platform uses the strongest available identity signal to avoid double-counting:

| Platform | Primary Key | Fallback | Rationale |
|----------|-------------|----------|-----------|
| **GitHub** | Login handle | — | GitHub's API returns the authenticated user's login, which is globally unique |
| **GitLab** | Commit email | Commit author name | GitLab commits expose email; cross-project dedup uses email as key |
| **Bitbucket Cloud** | `account_id` | Email → raw author string | `account_id` is the most stable Bitbucket identity |
| **Bitbucket Server** | Email | Author display name | Server API exposes `emailAddress` on commit authors |
| **Azure DevOps** | Email | Author name | ADO commit authors have `email` and `name` fields |

**Trade-off**: A developer using different email addresses across repos may be counted more than once. This is an accepted limitation — there's no universal cross-platform identity. The `--list-contributors` flag helps users spot duplicates manually.

## Bot Detection

The `_is_bot()` function applies three heuristic layers:

1. **Suffix check**: Names ending in `[bot]` (e.g., `dependabot[bot]`)
2. **Known names**: Exact matches against common CI/CD service accounts (dependabot, renovate, snyk, codecov, mergify, build service, etc.)
3. **Email patterns**: Addresses containing `noreply`, `bot@`, `builds@`, `pipeline@`

On GitHub, the API's `type: "Bot"` field provides an additional authoritative signal.

Bot detection is opt-in via `--exclude-bots` to avoid accidentally filtering legitimate contributors whose names or emails happen to match a pattern.

## Output Formats

All scripts produce three output formats:

### Text
- Progress indicators during scan (`[1/42] repo-name ... 156 commits`)
- Summary box at the end with contributor count
- Optional contributor list with `--list-contributors`
- Warnings and diagnostics go to **stderr** (so stdout can be redirected cleanly)

### JSON
- Structured payload for automation and piping
- Consistent keys across platforms: `scan_date`, `days`, `unique_contributors`, `exclude_bots`, `skipped_repos`
- Platform-specific keys for org/workspace/project identification

### Markdown
- Shareable report with summary table, contributor table, and per-repo breakdown
- Collapsible `<details>` sections to keep reports scannable
- Suitable for pasting into PRs, Slack, Confluence, or saving as files

## Graceful Degradation

Scripts are designed to produce partial results rather than crash:

- **Per-repo error handling**: If a single repository fails (permission denied, timeout, empty repo), it's logged to stderr and added to `skipped_repos`. The scan continues with remaining repos.
- **Rate limit recovery**: 429 responses trigger an automatic wait-and-retry cycle rather than failing.
- **Network resilience**: The retry adapter handles transient 5xx errors with exponential backoff.
- **Skipped repo reporting**: All output formats include the list of skipped repos so users know exactly what was missed.

## Verbose Mode

When `--verbose` is set, scripts emit diagnostic output to stderr at key points:

- Connection parameters (org URL, time window, flags)
- Repository count after fetch
- Per-repo timing and commit count
- Scan summary (total contributors, commits, elapsed time)
- Bot filter counts when `--exclude-bots` is active

This output always goes to stderr, so it's safe to combine with `--format json` and redirect stdout.

## Design Decisions

**Why separate scripts instead of a unified CLI?**
Each platform has different authentication, API semantics, and edge cases. Keeping them separate means simpler code, fewer dependencies per script, and the ability to deploy only what you need.

**Why Click instead of argparse?**
Click provides better help formatting, type validation, and composability with less boilerplate. It's a lightweight dependency that significantly improves the CLI experience.

**Why generators for pagination?**
Commit fetching uses Python generators (`yield from`) so that memory usage stays constant regardless of how many commits exist. We never load all commits into memory at once.

**Why not async/concurrent across platforms?**
The scripts are designed for one platform at a time. GitHub uses `ThreadPoolExecutor` for concurrent repo scanning within a single org because its API supports it well. Other platforms either have stricter rate limits or simpler pagination that doesn't benefit as much from concurrency.
