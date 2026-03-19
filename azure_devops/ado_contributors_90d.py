#!/usr/bin/env python3
"""
Azure DevOps Contributors Count Tool

Purpose:
  Calculates the number of unique contributing developers in an Azure DevOps Project
  over a configurable time window (default: 90 days).

Requirements:
  Python 3.6+
  Dependencies: requests, click

Installation:
  pip install -r requirements.txt

Usage:
  export ADO_TOKEN=your_pat
  python ado_contributors_90d.py --org https://dev.azure.com/myorg --project myproject

  # Custom time window (e.g., 30 days)
  python ado_contributors_90d.py --org https://dev.azure.com/myorg --project myproject --days 30

  # JSON output
  python ado_contributors_90d.py --org https://dev.azure.com/myorg --project myproject --format json

  # Markdown report
  python ado_contributors_90d.py --org https://dev.azure.com/myorg --project myproject --format markdown

Token Scopes:
  - `Code (Read)`
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
# Bot detection
# ---------------------------------------------------------------------------

_BOT_SUFFIXES = ("[bot]",)
_BOT_NAME_KEYWORDS = (
    "build service", "dependabot", "renovate", "snyk", "codecov",
    "greenkeeper", "mergify", "project collection build service",
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
@click.option('--org', '-o', required=True, help='Azure DevOps Org URL (e.g. https://dev.azure.com/myorg).')
@click.option('--project', '-p', required=True, help='Project name.')
@click.option('--token', '-t', help='Personal Access Token. Overrides ADO_TOKEN env var.')
@click.option('--format', 'output_format', type=click.Choice(['text', 'json', 'markdown']), default='text', help='Output format.')
@click.option('--list-contributors', is_flag=True, help='List individual contributors and their emails.')
@click.option('--days', '-d', type=int, default=90, show_default=True, help='Number of days to look back for contributions.')
@click.option('--exclude-bots', is_flag=True, help='Exclude bot/service accounts from the contributor count.')
@click.option('--verbose', '-v', is_flag=True, help='Print API diagnostics to stderr.')
def main(org, project, token, output_format, list_contributors, days, exclude_bots, verbose):
    """
    Calculate unique contributors for an Azure DevOps Project over a configurable time window.
    """
    def vlog(msg: str) -> None:
        if verbose:
            click.echo(f"  [verbose] {msg}", err=True)

    if days < 1:
        click.echo("Error: --days must be at least 1.", err=True)
        sys.exit(1)

    if not token:
        token = os.environ.get(ENV_VAR_TOKEN)
    if not token:
        click.echo("Error: ADO_TOKEN is required.", err=True)
        sys.exit(1)

    client = ADOClient(token, org)

    t0 = time.monotonic()
    now = datetime.datetime.now(datetime.timezone.utc)
    start_date = now - datetime.timedelta(days=days)

    since_iso = start_date.isoformat()
    until_iso = now.isoformat()

    vlog(f"Organization URL: {org}")
    vlog(f"Project: {project}")
    vlog(f"Time window: {start_date.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')} ({days} days)")
    vlog(f"Exclude bots: {exclude_bots}")

    # -- Fetch repos ---------------------------------------------------------
    if output_format == "text":
        click.echo(f"Fetching repositories for {project} ...")

    try:
        repos = fetch_repos(client, project)
    except ApiError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    total_repos = len(repos)
    vlog(f"Found {total_repos} repositories")
    if output_format == "text":
        click.echo(f"  Found {total_repos} repositories.\n")

    # -- Scan repos ----------------------------------------------------------
    contributors_map: Dict[str, Set[str]] = {}
    repo_commit_counts: List[Tuple[str, int]] = []
    skipped_repos: List[str] = []
    total_commits = 0
    bots_filtered = 0

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

        repo_t0 = time.monotonic()
        commit_count = 0
        repo_failed = False
        try:
            for commit in _fetch_commits(
                client, project, repo_id, since_iso, until_iso,
            ):
                commit_count += 1
                author = commit.get("author", {})
                email: Optional[str] = author.get("email")
                name: Optional[str] = author.get("name")

                if exclude_bots and _is_bot(name or "", email):
                    bots_filtered += 1
                    continue

                identifier = email if email else name
                if identifier:
                    if identifier not in contributors_map:
                        contributors_map[identifier] = set()
                    if email:
                        contributors_map[identifier].add(email)
        except Exception as exc:
            repo_failed = True
            skipped_repos.append(repo_name)
            click.echo(f"\n  Warning: skipped {repo_name}: {exc}", err=True)

        total_commits += commit_count
        repo_commit_counts.append((repo_name, commit_count))
        repo_elapsed = time.monotonic() - repo_t0
        vlog(f"{repo_name}: {commit_count} commits in {_elapsed(repo_elapsed)}")

        if output_format == "text" and not repo_failed:
            click.echo(f" {commit_count:,} commits")

    elapsed = time.monotonic() - t0
    total_contributors = len(contributors_map)

    if skipped_repos and output_format == "text":
        click.echo(f"\n  Warning: {len(skipped_repos)} repo(s) skipped due to errors.", err=True)

    vlog(f"Scan complete in {_elapsed(elapsed)}: {total_contributors} contributors, "
         f"{total_commits:,} commits across {total_repos} repos")
    if exclude_bots:
        vlog(f"Bot commits filtered: {bots_filtered}")

    # -- Output --------------------------------------------------------------
    if output_format == "json":
        payload: Dict[str, Any] = {
            "org": org,
            "project": project,
            "scan_date": now.strftime('%Y-%m-%d'),
            "days": days,
            "exclude_bots": exclude_bots,
            "unique_contributors": total_contributors,
            "repositories_scanned": total_repos,
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
            f"# Contributors Report — Azure DevOps",
            "",
            "| Field | Value |",
            "|-------|-------|",
            f"| **Organization** | {org} |",
            f"| **Project** | {project} |",
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
        click.echo(f"Organization: {org}")
        click.echo(f"Project: {project}")
        click.echo(f"Scan Date: {now.strftime('%Y-%m-%d')}")
        click.echo(f"Repositories scanned: {total_repos}")
        click.echo(f"Bots excluded: {'Yes' if exclude_bots else 'No'}")
        click.echo("-" * 40)
        click.echo(f"Contributors in last {days} days: {total_contributors}")

        if list_contributors:
            click.echo("-" * 40)
            click.echo("Contributors:")
            for ident in sorted(contributors_map.keys()):
                emails = ", ".join(sorted(contributors_map[ident]))
                click.echo(f"  - {ident} ({emails})")

        click.echo("="*40)

if __name__ == '__main__':
    main()
