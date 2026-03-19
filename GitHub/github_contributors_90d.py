#!/usr/bin/env python3
"""
GitHub Contributors Count Tool

Purpose:
  Calculates the number of unique contributing developers in a GitHub organization
  over a configurable time window (default: 90 days).

Requirements:
  Python 3.6+
  Dependencies: requests, click

Installation:
  pip install -r requirements.txt

Usage:
  export GITHUB_TOKEN=ghp_...
  python github_contributors_90d.py --org my-org

  # Custom time window (e.g., 30 days)
  python github_contributors_90d.py --org my-org --days 30

  # JSON output
  python github_contributors_90d.py --org my-org --format json

Token permissions (fine-grained):
  Repository  -> Metadata: Read-only, Contents: Read-only
  Organization -> Members: Read-only
"""

import os
import re
import sys
import json
import time
import datetime
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, Any, Set, List, Tuple, Generator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import click

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_BASE_URL = "https://api.github.com"
ENV_VAR_TOKEN = "GITHUB_TOKEN"
REQUEST_TIMEOUT: Tuple[int, int] = (10, 30)  # (connect, read) seconds
DEFAULT_WORKERS = 4
PER_PAGE = 100

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize(text: str, max_len: int = 300) -> str:
    """Truncate and strip embedded credentials from error text."""
    if not text:
        return "Unknown error"
    text = re.sub(r"://[^@/]+@", "://***@", text)
    return text[:max_len]


def _elapsed(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s" if m else f"{s}s"


def _summary_box(title: str, rows: List[Tuple[str, str]],
                 result_label: str, result_value: str) -> None:
    """Print a consistently-formatted summary table."""
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
# Exceptions
# ---------------------------------------------------------------------------

class ApiError(Exception):
    """Non-success response from the GitHub API."""
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}: {_sanitize(message)}")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class GitHubClient:
    """Thread-safe GitHub REST API client with retry and rate-limit support."""

    def __init__(self, token: Optional[str],
                 base_url: str = DEFAULT_BASE_URL) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._local = threading.local()
        self._print_lock = threading.Lock()

    def __repr__(self) -> str:
        return (f"GitHubClient(base_url={self._base_url!r}, "
                f"authenticated={self._token is not None})")

    # -- Thread-local session ------------------------------------------------

    @property
    def _session(self) -> requests.Session:
        """One connection-pooled session per thread."""
        if not hasattr(self._local, "session"):
            s = requests.Session()
            if self._token:
                s.headers["Authorization"] = f"token {self._token}"
            s.headers["Accept"] = "application/vnd.github.v3+json"
            s.headers["User-Agent"] = "contributors-count/1.0"

            retry = Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[500, 502, 503, 504],
                allowed_methods=["GET"],
                raise_on_status=False,
            )
            adapter = HTTPAdapter(
                max_retries=retry, pool_connections=10, pool_maxsize=10,
            )
            s.mount("https://", adapter)
            s.mount("http://", adapter)
            self._local.session = s
        return self._local.session

    # -- Core request --------------------------------------------------------

    def _get(self, url: str,
             params: Optional[Dict[str, Any]] = None) -> requests.Response:
        while True:
            try:
                resp = self._session.get(
                    url, params=params, timeout=REQUEST_TIMEOUT,
                )
            except requests.ConnectionError:
                raise ApiError(
                    0, "Connection failed. Check network and --base-url.",
                )
            except requests.Timeout:
                raise ApiError(
                    0, f"Request timed out after {REQUEST_TIMEOUT[1]}s.",
                )

            # GitHub primary rate limit: 403 + remaining == 0
            if resp.status_code == 403:
                remaining = resp.headers.get("X-RateLimit-Remaining")
                if remaining is not None and int(remaining) == 0:
                    reset_ts = int(resp.headers.get("X-RateLimit-Reset", 0))
                    wait = max(1, reset_ts - int(time.time()) + 1)
                    with self._print_lock:
                        click.echo(
                            f"  Rate limit hit. Waiting {wait}s ...",
                            err=True,
                        )
                    time.sleep(wait)
                    continue

            # Secondary / standard 429
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 60))
                with self._print_lock:
                    click.echo(
                        f"  Rate limit hit. Waiting {retry_after}s ...",
                        err=True,
                    )
                time.sleep(retry_after)
                continue

            if resp.status_code != 200:
                try:
                    msg = resp.json().get("message", resp.text[:300])
                except (ValueError, KeyError):
                    msg = resp.text[:300]
                raise ApiError(resp.status_code, msg)

            return resp

    # -- Paginated GET -------------------------------------------------------

    def get_paginated(self, endpoint: str,
                      params: Optional[Dict[str, Any]] = None,
                      ) -> Generator[Dict[str, Any], None, None]:
        if params is None:
            params = {}
        params["per_page"] = PER_PAGE

        url = f"{self._base_url}{endpoint}"
        while url:
            resp = self._get(url, params=params)
            data = resp.json()

            if isinstance(data, list):
                yield from data
            else:
                yield data
                return

            url = resp.links.get("next", {}).get("url")
            params = {}  # encoded in the next URL


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_repos(client: GitHubClient, org: str,
                max_repos: Optional[int] = None) -> List[Dict[str, Any]]:
    """Eagerly fetch all repos so we know the total count for progress."""
    repos: List[Dict[str, Any]] = []
    for repo in client.get_paginated(f"/orgs/{org}/repos"):
        repos.append(repo)
        if max_repos and len(repos) >= max_repos:
            break
    return repos


def _fetch_branches(client: GitHubClient, repo_full_name: str) -> List[str]:
    try:
        return [
            b["name"]
            for b in client.get_paginated(
                f"/repos/{repo_full_name}/branches",
            )
        ]
    except ApiError as exc:
        with client._print_lock:
            click.echo(
                f"  Warning: could not list branches for "
                f"{repo_full_name} ({exc})",
                err=True,
            )
        return []


def _fetch_commits(client: GitHubClient, repo_full_name: str,
                   since: str, until: str,
                   sha: Optional[str] = None,
                   ) -> Generator[Dict[str, Any], None, None]:
    params: Dict[str, str] = {"since": since, "until": until}
    if sha:
        params["sha"] = sha
    try:
        yield from client.get_paginated(
            f"/repos/{repo_full_name}/commits", params=params,
        )
    except ApiError as exc:
        with client._print_lock:
            click.echo(
                f"  Warning: commits skipped for "
                f"{repo_full_name} ({exc})",
                err=True,
            )


# ---------------------------------------------------------------------------
# Repo scanner (unit of work for the thread pool)
# ---------------------------------------------------------------------------

def _scan_repo(
    client: GitHubClient,
    repo: Dict[str, Any],
    since_iso: str,
    until_iso: str,
    default_branch_only: bool,
    exclude_bots: bool,
) -> Dict[str, Any]:
    """Scan a single repo; returns local contributor data (thread-safe)."""
    repo_name: str = repo["full_name"]
    default_branch: Optional[str] = repo.get("default_branch")

    if default_branch_only:
        branches = [default_branch] if default_branch else []
    else:
        branches = _fetch_branches(client, repo_name)

    local_contribs: Dict[str, Set[str]] = {}
    local_shas: Set[str] = set()
    commit_count = 0

    for branch in branches:
        for commit in _fetch_commits(
            client, repo_name, since_iso, until_iso, sha=branch,
        ):
            sha = commit.get("sha")
            if sha in local_shas:
                continue
            local_shas.add(sha)
            commit_count += 1

            author = commit.get("author")
            commit_author = commit.get("commit", {}).get("author", {})

            if not author or "login" not in author:
                continue

            login: str = author["login"]
            if exclude_bots:
                if (author.get("type") == "Bot"
                        or login.lower().endswith("[bot]")):
                    continue

            email: Optional[str] = commit_author.get("email")
            if login not in local_contribs:
                local_contribs[login] = set()
            if email:
                local_contribs[login].add(email)

    return {
        "repo_name": repo_name,
        "branch_count": len(branches),
        "commit_count": commit_count,
        "contributors": local_contribs,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option('--org', '-o', required=True, help='GitHub organization name.')
@click.option('--token', '-t', help='GitHub Personal Access Token. Overrides GITHUB_TOKEN env var.')
@click.option('--base-url', default=DEFAULT_BASE_URL, help='GitHub API Base URL.')
@click.option('--format', 'output_format', type=click.Choice(['text', 'json']), default='text', help='Output format.')
@click.option('--max-repos', type=int, help='Limit the number of repositories to process (for testing/large orgs).')
@click.option('--list-contributors', is_flag=True, help='List individual contributors and their emails.')
@click.option('--default-branch-only', is_flag=True, help='Only count commits from each repository\'s default branch.')
@click.option('--exclude-bots', is_flag=True, help='Exclude bot accounts from the contributor count.')
@click.option('--days', '-d', type=int, default=90, show_default=True, help='Number of days to look back for contributions.')
def main(org, token, base_url, output_format, max_repos, list_contributors, default_branch_only, exclude_bots, days):
    """
    Calculate unique contributors for a GitHub Org over a configurable time window.
    """
    if days < 1:
        click.echo("Error: --days must be at least 1.", err=True)
        sys.exit(1)

    # Resolve token
    if not token:
        token = os.environ.get(ENV_VAR_TOKEN)
    if not token and output_format == "text":
        click.echo(
            "Note: No token provided. Using anonymous access "
            "(lower rate limits).",
            err=True,
        )

    client = GitHubClient(token, base_url)

    t0 = time.monotonic()
    now = datetime.datetime.now(datetime.timezone.utc)
    start_date = now - datetime.timedelta(days=days)
    
    # ISO 8601 format for GitHub API
    since_iso = start_date.isoformat()
    until_iso = now.isoformat()

    # -- Fetch repo list -----------------------------------------------------
    if output_format == "text":
        click.echo(f"Fetching repositories for {org} ...")

    try:
        repos = fetch_repos(client, org, max_repos)
    except ApiError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    total_repos = len(repos)
    if output_format == "text":
        click.echo(f"  Found {total_repos} repositories.\n")

    if total_repos == 0:
        if output_format == "json":
            click.echo(json.dumps({
                "org": org, "scan_date": now.strftime("%Y-%m-%d"),
                "unique_contributors": 0, "repositories_scanned": 0,
            }, indent=2))
        else:
            click.echo("  No repositories found.")
        sys.exit(0)

    # -- Scan repos (threaded) -----------------------------------------------
    global_contribs: Dict[str, Set[str]] = {}
    completed = 0
    total_commits = 0
    workers = min(DEFAULT_WORKERS, total_repos)

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    _scan_repo, client, repo,
                    since_iso, until_iso,
                    default_branch_only, exclude_bots,
                ): repo
                for repo in repos
            }

            for future in as_completed(futures):
                completed += 1
                try:
                    result = future.result()
                except Exception as exc:
                    if output_format == "text":
                        click.echo(
                            f"  Warning: repo scan failed: {exc}", err=True,
                        )
                    continue

                # Merge results into global map
                for login, emails in result["contributors"].items():
                    if login not in global_contribs:
                        global_contribs[login] = set()
                    global_contribs[login].update(emails)

                total_commits += result["commit_count"]

                if output_format == "text":
                    rn = result["repo_name"]
                    bc = result["branch_count"]
                    cc = result["commit_count"]
                    pad = len(str(total_repos))
                    b_label = (
                        "default branch"
                        if default_branch_only
                        else f"{bc} branch{'es' if bc != 1 else ''}"
                    )
                    click.echo(
                        f"  [{completed:>{pad}}/{total_repos}] "
                        f"{rn} ({b_label}) "
                        f"... {cc:,} commits"
                    )

    except KeyboardInterrupt:
        click.echo("\nScan interrupted by user.", err=True)
        sys.exit(130)

    elapsed = time.monotonic() - t0
    total_contributors = len(global_contribs)

    # -- Output --------------------------------------------------------------
    if output_format == "json":
        payload: Dict[str, Any] = {
            "org": org,
            "scan_date": now.strftime('%Y-%m-%d'),
            "days": days,
            "default_branch_only": default_branch_only,
            "exclude_bots": exclude_bots,
            "unique_contributors": total_contributors
        }
        if list_contributors:
            payload["contributors_details"] = [
                {"login": login, "emails": sorted(emails)}
                for login, emails in sorted(global_contribs.items())
            ]
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo("\n" + "="*40)
        click.echo(f"Organization: {org}")
        click.echo(f"Scan Date: {now.strftime('%Y-%m-%d')}")
        click.echo(f"Repositories scanned: {total_repos}")
        click.echo(f"Default branch only: {'Yes' if default_branch_only else 'No'}")
        click.echo(f"Bots excluded: {'Yes' if exclude_bots else 'No'}")
        click.echo("-" * 40)
        click.echo(f"Contributors in last {days} days: {total_contributors}")
        
        if list_contributors:
            click.echo("\n  Contributors:")
            for login in sorted(global_contribs):
                emails_str = (
                    ", ".join(sorted(global_contribs[login])) or "N/A"
                )
                click.echo(f"    {login:<30} {emails_str}")
            click.echo()


if __name__ == "__main__":
    main()
