#!/usr/bin/env python3
"""
Bitbucket Server / Data Center Contributors Count Tool

Purpose:
  Calculates the number of unique contributing developers in a Bitbucket Server Project
  over a configurable time window (default: 90 days).

Requirements:
  Python 3.6+
  Dependencies: requests, click

Installation:
  pip install -r requirements.txt

Usage:
  export BITBUCKET_USER=myuser
  export BITBUCKET_PASSWORD=mypassword
  python bitbucket_server_contributors_90d.py --project MYPROJ

  # Custom time window (e.g., 30 days)
  python bitbucket_server_contributors_90d.py --project MYPROJ --days 30

  # Output formats: text, json, or markdown
  python bitbucket_server_contributors_90d.py --project MYPROJ --format json
  python bitbucket_server_contributors_90d.py --project MYPROJ --format markdown

Token permissions:
  Project / Repository Read
"""

import os
import re
import sys
import json
import time
import datetime
from typing import Optional, Dict, Any, Set, List, Tuple, Generator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import click

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ENV_VAR_URL = "BITBUCKET_SERVER_URL"
ENV_VAR_USER = "BITBUCKET_USER"
ENV_VAR_PASSWORD = "BITBUCKET_PASSWORD"
REQUEST_TIMEOUT: Tuple[int, int] = (10, 30)
PAGE_LIMIT = 100

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize(text: str, max_len: int = 300) -> str:
    if not text:
        return "Unknown error"
    text = re.sub(r"://[^@/]+@", "://***@", text)
    return text[:max_len]


def _elapsed(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s" if m else f"{s}s"


def _summary_box(title: str, rows: List[Tuple[str, str]],
                 result_label: str, result_value: str) -> None:
    w = 48
    click.echo()
    click.echo("=" * w)
    click.echo(f"  {title}")
    click.echo("=" * w)
    for label, value in rows:
        click.echo(f"  {label:<26}{value}")
    click.echo("-" * w)
    click.echo(f"  {result_label:<26}{result_value}")
    click.echo("=" * w)


# ---------------------------------------------------------------------------
# Bot detection
# ---------------------------------------------------------------------------

_BOT_SUFFIXES = ("[bot]",)
_BOT_NAME_KEYWORDS = (
    "build service", "dependabot", "renovate", "snyk", "codecov",
    "greenkeeper", "mergify", "bitbucket-pipelines",
)
_BOT_EMAIL_KEYWORDS = ("noreply", "[bot]", "bot@", "builds@", "pipeline@")


def _is_bot(name: str, email: Optional[str] = None) -> bool:
    """Heuristic check for automated / service accounts."""
    if not name:
        return False
    lower = name.lower()
    if any(lower.endswith(s) for s in _BOT_SUFFIXES):
        return True
    if any(k in lower for k in _BOT_NAME_KEYWORDS):
        return True
    if email:
        email_lower = email.lower()
        if any(k in email_lower for k in _BOT_EMAIL_KEYWORDS):
            return True
    return False


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ApiError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}: {_sanitize(message)}")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class BitbucketServerClient:
    """Bitbucket Server REST API client with retry and rate-limit support."""

    def __init__(self, base_url: str, user: str, password: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._session = requests.Session()

        if user and password:
            self._session.auth = (user, password)

        self._session.headers["User-Agent"] = "contributors-count/1.0"

        retry = Retry(
            total=3, backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"], raise_on_status=False,
        )
        adapter = HTTPAdapter(
            max_retries=retry, pool_connections=10, pool_maxsize=10,
        )
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

    def __repr__(self) -> str:
        return (f"BitbucketServerClient(base_url={self._base_url!r}, "
                f"authenticated={self._session.auth is not None})")

    # -- Core request --------------------------------------------------------

    def _get(self, endpoint: str,
             params: Optional[Dict[str, Any]] = None) -> requests.Response:
        url = f"{self._base_url}{endpoint}"
        while True:
            try:
                resp = self._session.get(
                    url, params=params, timeout=REQUEST_TIMEOUT,
                )
            except requests.ConnectionError:
                raise ApiError(
                    0, "Connection failed. Check network and --url.",
                )
            except requests.Timeout:
                raise ApiError(
                    0, f"Request timed out after {REQUEST_TIMEOUT[1]}s.",
                )

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 60))
                click.echo(
                    f"  Rate limit hit. Waiting {retry_after}s ...",
                    err=True,
                )
                time.sleep(retry_after)
                continue

            if resp.status_code != 200:
                try:
                    errors = resp.json().get("errors", [])
                    msg = errors[0].get("message", resp.text[:300]) if errors else resp.text[:300]
                except (ValueError, KeyError, IndexError):
                    msg = resp.text[:300]
                raise ApiError(resp.status_code, msg)

            return resp

    # -- Paginated GET (offset-based) ----------------------------------------

    def get_paginated(self, endpoint: str,
                      params: Optional[Dict[str, Any]] = None,
                      ) -> Generator[Dict[str, Any], None, None]:
        if params is None:
            params = {}
        params["limit"] = PAGE_LIMIT
        start = 0

        while True:
            params["start"] = start
            resp = self._get(endpoint, params=params)
            data = resp.json()

            items = data.get("values", [])
            yield from items

            if data.get("isLastPage", True):
                break

            next_start = data.get("nextPageStart")
            start = next_start if next_start is not None else start + len(items)


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_repos(client: BitbucketServerClient,
                project_key: str) -> List[Dict[str, Any]]:
    repos: List[Dict[str, Any]] = []
    endpoint = f"/rest/api/1.0/projects/{project_key}/repos"
    for repo in client.get_paginated(endpoint):
        repos.append(repo)
    return repos


def _fetch_commits(
    client: BitbucketServerClient,
    project_key: str,
    repo_slug: str,
    since_timestamp_ms: int,
) -> Generator[Dict[str, Any], None, None]:
    """Yield commits newer than *since_timestamp_ms*.

    Bitbucket Server returns commits in reverse-chronological order.
    We stop iterating as soon as we see a commit older than our window.
    """
    endpoint = (
        f"/rest/api/1.0/projects/{project_key}/repos/{repo_slug}/commits"
    )
    start = 0

    try:
        while True:
            params = {"start": start, "limit": PAGE_LIMIT}
            resp = client._get(endpoint, params=params)
            data = resp.json()

            items = data.get("values", [])
            if not items:
                break

            for commit in items:
                if commit.get("authorTimestamp", 0) < since_timestamp_ms:
                    return  # older than window
                yield commit

            if data.get("isLastPage", True):
                break

            next_start = data.get("nextPageStart")
            start = (
                next_start if next_start is not None else start + len(items)
            )

    except ApiError as exc:
        click.echo(
            f"  Warning: commits skipped for {repo_slug} ({exc})",
            err=True,
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option('--project', '-p', required=True, help='Bitbucket Project Key.')
@click.option('--url', required=True, help='Bitbucket Server Base URL (e.g. https://bitbucket.mycompany.com).')
@click.option('--user', '-u', help='Username. Overrides BITBUCKET_USER env var.')
@click.option('--password', '-pw', help='Password/Token. Overrides BITBUCKET_PASSWORD env var.')
@click.option('--format', 'output_format', type=click.Choice(['text', 'json', 'markdown']), default='text', help='Output format.')
@click.option('--list-contributors', is_flag=True, help='List individual contributors and their emails.')
@click.option('--days', '-d', type=int, default=90, show_default=True, help='Number of days to look back for contributions.')
@click.option('--exclude-bots', is_flag=True, help='Exclude bot/service accounts from the contributor count.')
@click.option('--verbose', '-v', is_flag=True, help='Print API diagnostics to stderr.')
def main(project, url, user, password, output_format, list_contributors, days, exclude_bots, verbose):
    """
    Calculate unique contributors for a Bitbucket Server Project over a configurable time window.
    """
    if days < 1:
        click.echo("Error: --days must be at least 1.", err=True)
        sys.exit(1)

    def vlog(msg: str) -> None:
        if verbose:
            click.echo(f"  [verbose] {msg}", err=True)

    if not user:
        user = os.environ.get(ENV_VAR_USER)
    if not password:
        password = os.environ.get(ENV_VAR_PASSWORD)

    if not user or not password:
        click.echo(
            "Error: BITBUCKET_USER and BITBUCKET_PASSWORD are required.",
            err=True,
        )
        sys.exit(1)

    client = BitbucketServerClient(url, user, password)

    t0 = time.monotonic()
    now = datetime.datetime.now(datetime.timezone.utc)
    start_date = now - datetime.timedelta(days=days)
    
    # Bitbucket Server uses milliseconds timestamp
    since_timestamp_ms = int(start_date.timestamp() * 1000)

    vlog(f"Project: {project}")
    vlog(f"Server URL: {url}")
    vlog(f"Time window: {start_date.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')} ({days} days)")
    vlog(f"Exclude bots: {exclude_bots}")

    # -- Fetch repos ---------------------------------------------------------
    if output_format == "text":
        click.echo(f"Fetching repositories for project {project} ...")

    try:
        repos = fetch_repos(client, project)
    except ApiError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    total_repos = len(repos)
    vlog(f"Repositories found: {total_repos}")
    if output_format == "text":
        click.echo(f"  Found {total_repos} repositories.\n")

    # -- Scan repos ----------------------------------------------------------
    contributors_map: Dict[str, Set[str]] = {}
    total_commits = 0
    repo_commit_counts: List[Tuple[str, int]] = []
    skipped_repos: List[str] = []
    bots_filtered = 0

    for idx, repo in enumerate(repos, 1):
        repo_name: str = repo["name"]
        repo_slug: str = repo["slug"]

        if output_format == "text":
            pad = len(str(total_repos))
            click.echo(
                f"  [{idx:>{pad}}/{total_repos}] {repo_name} ...",
                nl=False,
            )
            sys.stdout.flush()

        repo_t0 = time.monotonic() if verbose else 0
        commit_count = 0
        try:
            for commit in _fetch_commits(
                client, project, repo_slug, since_timestamp_ms,
            ):
                author = commit.get("author", {})
                email: Optional[str] = author.get("emailAddress")
                name: Optional[str] = author.get("name")

                if exclude_bots and _is_bot(name or "", email):
                    bots_filtered += 1
                    continue

                commit_count += 1
                identifier = email if email else name
                if identifier:
                    if identifier not in contributors_map:
                        contributors_map[identifier] = set()
                    if email:
                        contributors_map[identifier].add(email)
        except Exception as exc:
            skipped_repos.append(repo_name)
            vlog(f"Skipped {repo_name}: {exc}")
            if output_format == "text":
                click.echo(f" (skipped: {exc})")
            continue

        repo_commit_counts.append((repo_name, commit_count))
        total_commits += commit_count
        if verbose:
            vlog(f"{repo_name}: {commit_count:,} commits in {time.monotonic() - repo_t0:.2f}s")
        if output_format == "text":
            click.echo(f" {commit_count:,} commits")

    elapsed = time.monotonic() - t0
    total_contributors = len(contributors_map)

    if verbose:
        vlog(f"Scan complete: {total_contributors} contributors, {total_commits:,} commits, "
             f"{bots_filtered} bots filtered, {len(skipped_repos)} repos skipped")

    # -- Output --------------------------------------------------------------
    if output_format == "json":
        payload: Dict[str, Any] = {
            "project": project,
            "scan_date": now.strftime('%Y-%m-%d'),
            "days": days,
            "unique_contributors": total_contributors,
            "exclude_bots": exclude_bots,
            "skipped_repos": skipped_repos,
        }
        if list_contributors:
            payload["contributors_details"] = [
                {"identifier": ident, "emails": sorted(emails)}
                for ident, emails in sorted(contributors_map.items())
            ]
        click.echo(json.dumps(payload, indent=2))
    elif output_format == "markdown":
        lines = [
            f"# Contributors Report — Bitbucket Server",
            "",
            "| Field | Value |",
            "|-------|-------|",
            f"| **Project** | {project} |",
            f"| **Server URL** | {url} |",
            f"| **Scan Date** | {now.strftime('%Y-%m-%d')} |",
            f"| **Time Window** | {days} days |",
            f"| **Repositories Scanned** | {total_repos} |",
            f"| **Bots Excluded** | {'Yes' if exclude_bots else 'No'} |",
            f"| **Scan Duration** | {_elapsed(elapsed)} |",
            "",
            f"## Unique Contributors: {total_contributors}",
            "",
        ]
        if list_contributors and contributors_map:
            lines.append("| # | Contributor | Email(s) |")
            lines.append("|---|-------------|----------|")
            for i, ident in enumerate(sorted(contributors_map.keys()), 1):
                emails_str = ", ".join(sorted(contributors_map[ident])) or "N/A"
                lines.append(f"| {i} | {ident} | {emails_str} |")
            lines.append("")
        if repo_commit_counts:
            lines.append("<details>")
            lines.append("<summary>Per-Repository Breakdown</summary>")
            lines.append("")
            lines.append("| Repository | Commits |")
            lines.append("|------------|---------|")
            for rname, rcount in sorted(repo_commit_counts, key=lambda x: x[1], reverse=True):
                lines.append(f"| {rname} | {rcount:,} |")
            lines.append("")
            lines.append("</details>")
            lines.append("")
        if skipped_repos:
            lines.append(f"> **Note:** {len(skipped_repos)} repo(s) skipped due to errors: "
                         + ", ".join(skipped_repos))
            lines.append("")
        lines.append("---")
        lines.append("*Generated by [Contributors-Count](https://github.com/nicklhw/Contributors-Count)*")
        click.echo("\n".join(lines))
    else:
        click.echo("\n" + "="*40)
        click.echo(f"Project: {project}")
        click.echo(f"Scan Date: {now.strftime('%Y-%m-%d')}")
        click.echo(f"Repositories scanned: {total_repos}")
        click.echo(f"Bots excluded: {'Yes' if exclude_bots else 'No'}")
        click.echo("-" * 40)
        click.echo(f"Contributors in last {days} days: {total_contributors}")
        
        if list_contributors:
            click.echo("\n  Contributors:")
            for ident in sorted(contributors_map):
                emails_str = (
                    ", ".join(sorted(contributors_map[ident])) or "N/A"
                )
                click.echo(f"    {ident:<30} {emails_str}")
            click.echo()


if __name__ == "__main__":
    main()
