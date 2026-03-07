#!/usr/bin/env python3
"""
Azure DevOps Contributors Count Tool

Calculates the number of unique contributing developers in an Azure DevOps
Project over the last 90 days.

Usage:
  export ADO_TOKEN=your_pat
  python ado_contributors_90d.py --org https://dev.azure.com/myorg --project myproject

Token scopes:
  Code (Read)
"""

import os
import re
import sys
import json
import time
import base64
import datetime
from typing import Optional, Dict, Any, Set, List, Tuple, Generator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import click

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ENV_VAR_TOKEN = "ADO_TOKEN"
REQUEST_TIMEOUT: Tuple[int, int] = (10, 30)
ADO_API_VERSION = "7.1"

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

class ADOClient:
    """Azure DevOps REST API client with retry and rate-limit support."""

    def __init__(self, token: str, org_url: str) -> None:
        self._org_url = org_url.rstrip("/")
        self._session = requests.Session()

        # ADO uses Basic Auth with empty username + PAT as password
        if token:
            b64 = base64.b64encode(f":{token}".encode()).decode()
            self._session.headers["Authorization"] = f"Basic {b64}"

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
        return (f"ADOClient(org_url={self._org_url!r}, "
                f"authenticated={'Authorization' in self._session.headers})")

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
                    0, "Connection failed. Check network and --org URL.",
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
                    msg = resp.json().get("message", resp.text[:300])
                except (ValueError, KeyError):
                    msg = resp.text[:300]
                raise ApiError(resp.status_code, msg)

            return resp

    # -- Paginated GET (continuation-token based) ----------------------------

    def get_paginated(self, url: str,
                      params: Optional[Dict[str, Any]] = None,
                      ) -> Generator[Dict[str, Any], None, None]:
        if params is None:
            params = {}

        while True:
            resp = self._get(url, params=params)
            data = resp.json()
            yield from data.get("value", [])

            token = resp.headers.get("x-ms-continuationtoken")
            if not token:
                break
            params["continuationToken"] = token


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_repos(client: ADOClient,
                project: str) -> List[Dict[str, Any]]:
    url = (
        f"{client._org_url}/{project}"
        f"/_apis/git/repositories?api-version={ADO_API_VERSION}"
    )
    repos: List[Dict[str, Any]] = []
    for repo in client.get_paginated(url):
        repos.append(repo)
    return repos


def _fetch_commits(
    client: ADOClient,
    project: str,
    repo_id: str,
    since: str,
    until: str,
) -> Generator[Dict[str, Any], None, None]:
    url = (
        f"{client._org_url}/{project}"
        f"/_apis/git/repositories/{repo_id}"
        f"/commits?api-version={ADO_API_VERSION}"
    )
    params = {
        "searchCriteria.fromDate": since,
        "searchCriteria.toDate": until,
        "searchCriteria.$top": 10000,
    }
    try:
        yield from client.get_paginated(url, params=params)
    except ApiError as exc:
        click.echo(
            f"  Warning: commits skipped for repo {repo_id} ({exc})",
            err=True,
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option("--org", "-o", required=True,
              help="Azure DevOps Org URL (e.g. https://dev.azure.com/myorg).")
@click.option("--project", "-p", required=True,
              help="Project name.")
@click.option("--token", "-t",
              help="Personal Access Token (overrides ADO_TOKEN env var).")
@click.option("--format", "output_format",
              type=click.Choice(["text", "json"]), default="text",
              help="Output format.")
@click.option("--list-contributors", is_flag=True,
              help="Include per-contributor detail in output.")
def main(
    org: str,
    project: str,
    token: Optional[str],
    output_format: str,
    list_contributors: bool,
) -> None:
    """Count unique contributors for an Azure DevOps Project over the last 90 days."""
    t0 = time.monotonic()

    if not token:
        token = os.environ.get(ENV_VAR_TOKEN)
    if not token:
        click.echo("Error: ADO_TOKEN is required.", err=True)
        sys.exit(1)

    client = ADOClient(token, org)

    now = datetime.datetime.now(datetime.timezone.utc)
    since_iso = (now - datetime.timedelta(days=90)).isoformat()
    until_iso = now.isoformat()

    # -- Fetch repos ---------------------------------------------------------
    if output_format == "text":
        click.echo(f"Fetching repositories for {project} ...")

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
        repo_id: str = repo["id"]

        if output_format == "text":
            pad = len(str(total_repos))
            click.echo(
                f"  [{idx:>{pad}}/{total_repos}] {repo_name} ...",
                nl=False,
            )
            sys.stdout.flush()

        commit_count = 0
        for commit in _fetch_commits(
            client, project, repo_id, since_iso, until_iso,
        ):
            commit_count += 1
            author = commit.get("author", {})
            email: Optional[str] = author.get("email")
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
            "org": org,
            "project": project,
            "scan_date": now.strftime("%Y-%m-%d"),
            "repositories_scanned": total_repos,
            "elapsed_seconds": round(elapsed, 1),
            "contributors_90d": total_contributors,
        }
        if list_contributors:
            payload["contributors_details"] = [
                {"identifier": ident, "emails": sorted(emails)}
                for ident, emails in sorted(contributors_map.items())
            ]
        click.echo(json.dumps(payload, indent=2))
    else:
        rows: List[Tuple[str, str]] = [
            ("Organization:", org),
            ("Project:", project),
            ("Scan Date:", now.strftime("%Y-%m-%d")),
            ("Repositories Scanned:", str(total_repos)),
            ("Total Commits:", f"{total_commits:,}"),
            ("Elapsed:", _elapsed(elapsed)),
        ]
        _summary_box(
            "Azure DevOps Contributors - 90 Day Report",
            rows,
            "Unique Contributors:", str(total_contributors),
        )

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
