#!/usr/bin/env python3
"""
Bitbucket Cloud Contributors Count Tool

Purpose:
  Calculates the number of unique contributing developers in a Bitbucket Workspace
  over a configurable time window (default: 90 days).

Requirements:
  Python 3.6+
  Dependencies: requests, click

Installation:
  pip install -r requirements.txt

Usage:
  export BITBUCKET_USER=myuser
  export BITBUCKET_PASSWORD=my_app_password
  python bitbucket_contributors_90d.py --workspace myworkspace

  # Custom time window (e.g., 30 days)
  python bitbucket_contributors_90d.py --workspace myworkspace --days 30

  # JSON output
  python bitbucket_contributors_90d.py --workspace myworkspace --format json

Token Scopes:
  - `Repositories: Read`
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
DEFAULT_BASE_URL = "https://api.bitbucket.org/2.0"
ENV_VAR_USER = "BITBUCKET_USER"
ENV_VAR_PASSWORD = "BITBUCKET_PASSWORD"
REQUEST_TIMEOUT: Tuple[int, int] = (10, 30)

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

class BitbucketClient:
    """Bitbucket Cloud REST API client with retry and rate-limit support."""

    def __init__(self, user: str, password: str,
                 base_url: str = DEFAULT_BASE_URL) -> None:
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
        return (f"BitbucketClient(base_url={self._base_url!r}, "
                f"authenticated={self._session.auth is not None})")

    # -- Core request --------------------------------------------------------

    def _get(self, url: str,
             params: Optional[Dict[str, Any]] = None) -> requests.Response:
        while True:
            try:
                resp = self._session.get(
                    url, params=params, timeout=REQUEST_TIMEOUT,
                )
            except requests.ConnectionError:
                raise ApiError(0, "Connection failed. Check network.")
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
                    msg = (resp.json()
                           .get("error", {})
                           .get("message", resp.text[:300]))
                except (ValueError, KeyError):
                    msg = resp.text[:300]
                raise ApiError(resp.status_code, msg)

            return resp

    # -- Paginated GET -------------------------------------------------------

    def get_paginated(self, url: str,
                      params: Optional[Dict[str, Any]] = None,
                      ) -> Generator[Dict[str, Any], None, None]:
        if params is None:
            params = {}

        while url:
            resp = self._get(url, params=params)
            data = resp.json()
            yield from data.get("values", [])
            url = data.get("next")
            params = {}  # encoded in next URL


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_repos(client: BitbucketClient,
                workspace: str) -> List[Dict[str, Any]]:
    repos: List[Dict[str, Any]] = []
    url = f"{client._base_url}/repositories/{workspace}"
    for repo in client.get_paginated(url):
        repos.append(repo)
    return repos


def _fetch_commits(client: BitbucketClient, workspace: str,
                   repo_slug: str,
                   since_iso: str) -> Generator[Dict[str, Any], None, None]:
    url = f"{client._base_url}/repositories/{workspace}/{repo_slug}/commits"
    params = {"q": f'date > "{since_iso}"'}
    try:
        yield from client.get_paginated(url, params=params)
    except ApiError as exc:
        click.echo(
            f"  Warning: commits skipped for {repo_slug} ({exc})",
            err=True,
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option('--workspace', '-w', required=True, help='Bitbucket Workspace ID/Slug.')
@click.option('--user', '-u', help='Bitbucket Username. Overrides BITBUCKET_USER env var.')
@click.option('--password', '-p', help='Bitbucket App Password. Overrides BITBUCKET_PASSWORD env var.')
@click.option('--format', 'output_format', type=click.Choice(['text', 'json']), default='text', help='Output format.')
@click.option('--list-contributors', is_flag=True, help='List individual contributors and their emails.')
@click.option('--days', '-d', type=int, default=90, show_default=True, help='Number of days to look back for contributions.')
def main(workspace, user, password, output_format, list_contributors, days):
    """
    Calculate unique contributors for a Bitbucket Workspace over a configurable time window.
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

    client = BitbucketClient(user, password)

    now = datetime.datetime.now(datetime.timezone.utc)
    start_date = now - datetime.timedelta(days=days)
    
    since_iso = start_date.isoformat()

    # -- Fetch repos ---------------------------------------------------------
    if output_format == "text":
        click.echo(f"Fetching repositories for {workspace} ...")

    try:
        repos = fetch_repos(client, workspace)
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
        for commit in _fetch_commits(client, workspace, repo_slug, since_iso):
            commit_count += 1
            author = commit.get("author", {})
            raw: Optional[str] = author.get("raw")
            user_info: Dict[str, Any] = author.get("user", {})

            identifier: Optional[str] = None
            email: Optional[str] = None

            if "account_id" in user_info:
                identifier = user_info["account_id"]
            elif raw:
                if "<" in raw and ">" in raw:
                    email = raw.split("<")[-1].strip(">")
                    identifier = email
                else:
                    identifier = raw

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
            "workspace": workspace,
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
        click.echo(f"Workspace: {workspace}")
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
