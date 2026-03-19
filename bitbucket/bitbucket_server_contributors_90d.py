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

  # JSON output
  python bitbucket_server_contributors_90d.py --project MYPROJ --format json

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
@click.option('--format', 'output_format', type=click.Choice(['text', 'json']), default='text', help='Output format.')
@click.option('--list-contributors', is_flag=True, help='List individual contributors and their emails.')
@click.option('--days', '-d', type=int, default=90, show_default=True, help='Number of days to look back for contributions.')
def main(project, url, user, password, output_format, list_contributors, days):
    """
    Calculate unique contributors for a Bitbucket Server Project over a configurable time window.
    """
    if days < 1:
        click.echo("Error: --days must be at least 1.", err=True)
        sys.exit(1)

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

    now = datetime.datetime.now(datetime.timezone.utc)
    start_date = now - datetime.timedelta(days=days)
    
    # Bitbucket Server uses milliseconds timestamp
    since_timestamp_ms = int(start_date.timestamp() * 1000)

    # -- Fetch repos ---------------------------------------------------------
    if output_format == "text":
        click.echo(f"Fetching repositories for project {project} ...")

    try:
        repos = fetch_repos(client, project)
    except ApiError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    total_repos = len(repos)
    if output_format == "text":
        click.echo(f"  Found {total_repos} repositories.\n")

    # -- Scan repos ----------------------------------------------------------
    contributors_map: Dict[str, Set[str]] = {}
    total_commits = 0

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

        commit_count = 0
        for commit in _fetch_commits(
            client, project, repo_slug, since_timestamp_ms,
        ):
            commit_count += 1
            author = commit.get("author", {})
            email: Optional[str] = author.get("emailAddress")
            name: Optional[str] = author.get("name")

            identifier = email if email else name
            if identifier:
                if identifier not in contributors_map:
                    contributors_map[identifier] = set()
                if email:
                    contributors_map[identifier].add(email)

        total_commits += commit_count
        if output_format == "text":
            click.echo(f" {commit_count:,} commits")

    elapsed = time.monotonic() - t0
    total_contributors = len(contributors_map)

    # -- Output --------------------------------------------------------------
    if output_format == "json":
        payload: Dict[str, Any] = {
            "project": project,
            "scan_date": now.strftime('%Y-%m-%d'),
            "days": days,
            "unique_contributors": total_contributors
        }
        if list_contributors:
            payload["contributors_details"] = [
                {"identifier": ident, "emails": sorted(emails)}
                for ident, emails in sorted(contributors_map.items())
            ]
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo("\n" + "="*40)
        click.echo(f"Project: {project}")
        click.echo(f"Scan Date: {now.strftime('%Y-%m-%d')}")
        click.echo(f"Repositories scanned: {repo_count}")
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
