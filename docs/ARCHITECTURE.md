# Architecture

This document describes the design patterns and decisions behind Contributors-Count.

## Overview

Contributors-Count is a collection of standalone Python CLI tools, one per platform, plus a unified cross-platform runner. Each per-platform script is fully self-contained — it can be copied to any machine with Python 3.6+ and its dependencies.

```
User
 │
 ├─ Per-platform scripts ──────────────────────────────────────┐
 │                                                             │
 │  ┌──────────────────────────────┐                           │
 │  │  CLI (Click)                 │  Parses flags, validates  │
 │  │  main()                      │  input, sets up auth      │
 │  ├──────────────────────────────┤                           │
 │  │  API Client                  │  HTTP session, retry,     │
 │  │  ADOClient / BitbucketClient │  rate-limit handling      │
 │  ├──────────────────────────────┤                           │
 │  │  Data Fetching               │  fetch_repos →            │
 │  │  Generators for lazy paging  │  _fetch_commits           │
 │  ├──────────────────────────────┤                           │
 │  │  Processing                  │  Dedup, bot filter, count │
 │  ├──────────────────────────────┤                           │
 │  │  Output                      │  text / json / markdown   │
 │  └──────────────────────────────┘                           │
 │                                                             │
 ├─ Unified runner (contributors_count.py) ────────────────────┤
 │                                                             │
 │  ┌──────────────────────────────┐                           │
 │  │  Config loader (JSON)        │  Reads platforms.json     │
 │  ├──────────────────────────────┤                           │
 │  │  Platform scanners           │  Imports & calls each     │
 │  │  _scan_github, _scan_gitlab  │  platform's internal      │
 │  │  _scan_bb_cloud, _scan_ado   │  functions directly       │
 │  ├──────────────────────────────┤                           │
 │  │  Cross-platform dedup        │  Union-Find by shared     │
 │  │  _UnionFind + _cross_dedup   │  email addresses          │
 │  ├──────────────────────────────┤                           │
 │  │  Consolidated output         │  text / json / markdown   │
 │  └──────────────────────────────┘                           │
 └─────────────────────────────────────────────────────────────┘
```

## Script Structure

Every per-platform script follows the same layout:

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

## API Client Pattern

Each platform has a client class that encapsulates:

- **Session setup**: `requests.Session` with auth headers, User-Agent, connection pooling
- **Retry strategy**: `urllib3.util.retry.Retry` with exponential backoff on 5xx errors
- **Rate limit handling**: 429 responses trigger a wait based on `Retry-After` header
- **Pagination**: Platform-specific (GitHub uses `Link` headers, ADO uses continuation tokens, Bitbucket uses `next` URLs, GitLab uses `python-gitlab`'s built-in pagination)

## Deduplication Strategy

### Per-Platform Deduplication

Each platform uses the strongest available identity signal:

| Platform | Primary Key | Fallback | Rationale |
|----------|-------------|----------|-----------|
| **GitHub** | Login handle | — | Globally unique per GitHub instance |
| **GitLab** | Commit email | Author name | Email is exposed on commits |
| **Bitbucket Cloud** | `account_id` | Email → raw string | `account_id` is the most stable identity |
| **Bitbucket Server** | Email | Author name | Server API exposes `emailAddress` |
| **Azure DevOps** | Email | Author name | ADO commits have `email` and `name` |

### Cross-Platform Deduplication (Unified Mode)

The unified runner merges contributors across platforms using a **union-find** (disjoint-set) algorithm:

1. Each contributor from each platform becomes a node: `(platform, identifier)`
2. For each email address, if two contributors share it, their nodes are merged
3. Transitive merging: if A shares an email with B, and B shares a different email with C, all three merge into one group
4. Contributors with no emails cannot be cross-deduped and remain separate

This handles the common case where a developer uses the same email on GitHub and GitLab but different usernames.

**Trade-off**: A developer using completely different email addresses across platforms will be counted separately. The `--list-contributors` flag helps users spot these manually.

## Bot Detection

The `_is_bot()` function applies three heuristic layers:

1. **Suffix check**: Names ending in `[bot]`
2. **Known names**: Common CI/CD service accounts (dependabot, renovate, snyk, codecov, mergify, build service)
3. **Email patterns**: Addresses containing `noreply`, `bot@`, `builds@`, `pipeline@`

On GitHub, the API's `type: "Bot"` field provides an additional authoritative signal.

## Output Formats

All scripts (per-platform and unified) produce three output formats:

- **Text**: Progress indicators, summary box, optional contributor list
- **JSON**: Structured payload for automation
- **Markdown**: Shareable report with tables and collapsible breakdowns

The unified runner adds cross-platform dedup stats (per-platform sum vs. deduplicated total) to all formats.

## Graceful Degradation

- Per-repo errors are caught and logged; the scan continues
- Skipped repos are tracked and reported in all output formats
- Rate limits trigger automatic wait-and-retry
- The unified runner continues scanning remaining platforms if one fails

## Design Decisions

**Why separate scripts instead of a unified CLI?**
Each platform has different authentication, API semantics, and edge cases. Keeping them separate means simpler code, fewer dependencies per script, and the ability to deploy only what you need. The unified runner sits on top without replacing the individual scripts.

**Why JSON config for the unified runner instead of CLI flags?**
Specifying credentials and org names for 5 platforms on one command line would be unwieldy. A JSON config file keeps it clean and avoids secrets on the command line (tokens come from env vars).

**Why union-find for cross-platform dedup?**
Email overlap can be transitive (A↔B via email1, B↔C via email2 → A, B, C are one person). A simple pairwise merge would miss these chains. Union-find handles arbitrary transitivity in near-linear time.

**Why Click instead of argparse?**
Click provides better help formatting, type validation, and composability with less boilerplate.

**Why generators for pagination?**
Commit fetching uses Python generators (`yield from`) so that memory usage stays constant regardless of commit volume.
