#!/usr/bin/env python3
"""
GitLab Contributors Count Tool

Purpose:
  Calculates the number of unique contributing developers across all accessible
  GitLab groups and projects over a configurable time window (default: 90 days).

Usage:
  export GITLAB_TOKEN=glpat-...
  python gitlab_contributor_count.py

  # Self-hosted GitLab
  python gitlab_contributor_count.py --url https://gitlab.mycompany.com

  # Custom time window (e.g., 30 days)
  python gitlab_contributor_count.py --days 30

  # JSON output
  python gitlab_contributor_count.py --format json

Token Scopes:
  - read_api
  - read_user
"""

import os
import sys
import json
import time
import datetime
from typing import Dict, Set, List, Tuple, Optional

import gitlab
import click

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_GITLAB_URL = "https://gitlab.com"
ENV_VAR_TOKEN = "GITLAB_TOKEN"
REQUEST_TIMEOUT = 30  # seconds

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _parse_commit_date(created_at: str) -> datetime.datetime:
    """Parse a GitLab commit timestamp into a datetime object."""
    try:
        return datetime.datetime.fromisoformat(created_at.rstrip("Z"))
    except ValueError:
        return datetime.datetime.strptime(
            created_at, "%Y-%m-%dT%H:%M:%S.%f%z",
        )


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _process_project(
    gl_client: gitlab.Gitlab,
    project_id: int,
    since_iso: str,
    contributors: Dict[str, dict],
    unique_contributors: Dict[str, dict],
    gitlab_url: str,
) -> int:
    """Process commits for a single project and update contributor maps.

    Uses author_email as the primary dedup key (falls back to author_name).
    Returns the number of commits processed.
    """
    try:
        project = gl_client.projects.get(project_id)
    except gitlab.exceptions.GitlabGetError as exc:
        click.echo(
            f"  Warning: could not access project {project_id} "
            f"({exc.response_code})",
            err=True,
        )
        return 0

    project_path: str = project.path_with_namespace

    try:
        commits = project.commits.list(since=since_iso, all=True)
    except gitlab.exceptions.GitlabListError as exc:
        click.echo(
            f"  Warning: could not list commits for {project_path} "
            f"({exc.response_code})",
            err=True,
        )
        return 0

    commit_count = 0
    for commit in commits:
        commit_count += 1
        email: Optional[str] = getattr(commit, "author_email", None)
        name: Optional[str] = getattr(commit, "author_name", None)
        identifier = email if email else name

        if not identifier:
            continue

        commit_date = _parse_commit_date(commit.created_at)
        info = {
            "name": name or "",
            "email": email or "",
            "date": commit_date,
            "sha": commit.id,
            "project_path": project_path,
        }

        if (identifier not in contributors
                or commit_date > contributors[identifier]["date"]):
            contributors[identifier] = info

        if (identifier not in unique_contributors
                or commit_date > unique_contributors[identifier]["date"]):
            unique_contributors[identifier] = info

    return commit_count


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option('--url', '-u', default=DEFAULT_GITLAB_URL,
              help='GitLab instance URL (default: https://gitlab.com).')
@click.option('--token', '-t', help='GitLab Personal Access Token. Overrides GITLAB_TOKEN env var.')
@click.option('--format', 'output_format', type=click.Choice(['text', 'json']), default='text',
              help='Output format.')
@click.option('--list-contributors', is_flag=True, help='List individual contributors and their emails.')
@click.option('--days', '-d', type=int, default=90, show_default=True, help='Number of days to look back for contributions.')
def main(url, token, output_format, list_contributors, days):
    """
    Calculate unique contributors across all accessible GitLab groups and projects
    over a configurable time window.
    """
    if days < 1:
        click.echo("Error: --days must be at least 1.", err=True)
        sys.exit(1)

    if not token:
        token = os.environ.get(ENV_VAR_TOKEN)
    if not token:
        click.echo(
            "Error: GITLAB_TOKEN is required. "
            "Set it via env var or --token.",
            err=True,
        )
        sys.exit(1)

    # python-gitlab handles retries and timeouts natively
    gl = gitlab.Gitlab(
        url,
        private_token=token,
        timeout=REQUEST_TIMEOUT,
        retry_transient_errors=True,
        user_agent="contributors-count/1.0",
    )

    t0 = time.monotonic()
    now = datetime.datetime.now(datetime.timezone.utc)
    start_date = now - datetime.timedelta(days=days)
    since_iso = start_date.isoformat()

    # group_name -> { identifier -> commit_info }
    all_contributors: Dict[str, Dict[str, dict]] = {}
    # global deduped: identifier -> commit_info
    unique_contributors: Dict[str, dict] = {}
    # avoid double-processing projects seen via groups
    scanned_project_ids: Set[int] = set()
    total_commits = 0

    # -- Scan group projects -------------------------------------------------
    if output_format == "text":
        click.echo("Fetching groups ...")

    try:
        groups = gl.groups.list(all=True)
    except gitlab.exceptions.GitlabListError as exc:
        click.echo(f"Error listing groups: {exc}", err=True)
        sys.exit(1)

    for group in groups:
        group_name: str = group.name
        if output_format == "text":
            click.echo(f"\n  Group: {group_name}")

        contributors: Dict[str, dict] = {}

        try:
            group_projects = group.projects.list(all=True)
        except gitlab.exceptions.GitlabListError:
            click.echo(
                f"  Warning: could not list projects in {group_name}",
                err=True,
            )
            all_contributors[group_name] = contributors
            continue

        for gp in group_projects:
            scanned_project_ids.add(gp.id)
            if output_format == "text":
                click.echo(f"    {gp.name} ...", nl=False)
                sys.stdout.flush()

            cc = _process_project(
                gl, gp.id, since_iso,
                contributors, unique_contributors, url,
            )
            total_commits += cc

            if output_format == "text":
                click.echo(f" {cc:,} commits")

        all_contributors[group_name] = contributors

    # -- Scan standalone / membership projects --------------------------------
    if output_format == "text":
        click.echo("\n  Standalone / membership projects:")

    standalone_contributors: Dict[str, dict] = {}
    try:
        membership_projects = gl.projects.list(membership=True, all=True)
    except gitlab.exceptions.GitlabListError as exc:
        click.echo(
            f"  Warning: could not list membership projects: {exc}",
            err=True,
        )
        membership_projects = []

    for project in membership_projects:
        if project.id in scanned_project_ids:
            continue
        scanned_project_ids.add(project.id)

        if output_format == "text":
            click.echo(f"    {project.name} ...", nl=False)
            sys.stdout.flush()

        cc = _process_project(
            gl, project.id, since_iso,
            standalone_contributors, unique_contributors, url,
        )
        total_commits += cc

        if output_format == "text":
            click.echo(f" {cc:,} commits")

    all_contributors["Standalone Projects"] = standalone_contributors

    elapsed = time.monotonic() - t0
    total_contributors = len(unique_contributors)
    total_projects = len(scanned_project_ids)

    # -- Output --------------------------------------------------------------
    if output_format == "json":
        payload = {
            "gitlab_url": url,
            "scan_date": now.strftime('%Y-%m-%d'),
            "days": days,
            "unique_contributors": total_contributors,
            "groups": {}
        }

        for group_name, contributors in all_contributors.items():
            payload["groups"][group_name] = {
                "unique_contributors": len(contributors)
            }
        if list_contributors:
            payload["contributors_details"] = [
                {
                    "identifier": ident,
                    "name": info["name"],
                    "email": info["email"],
                    "last_commit_date": info["date"].strftime(
                        "%Y-%m-%d %H:%M:%S",
                    ),
                    "last_commit_url": (
                        f"{url}/{info['project_path']}"
                        f"/-/commit/{info['sha']}"
                    ),
                }
                for ident, info in sorted(unique_contributors.items())
            ]
        click.echo(json.dumps(payload, indent=2))
    else:
        # Per-group summary
        for group_name, contributors in all_contributors.items():
            click.echo(f"\nContributing developers in {group_name}: {len(contributors)}")

            if list_contributors:
                for ident, info in sorted(contributors.items(), key=lambda x: x[1]['date'], reverse=True):
                    commit_url = f"{url}/{info['project_path']}/-/commit/{info['sha']}"
                    click.echo(f"  - {info['name']} ({info.get('email', 'N/A')}): "
                               f"{info['date'].strftime('%Y-%m-%d %H:%M:%S')} UTC")
                    click.echo(f"    Commit: {commit_url}")

        # Consolidated
        click.echo("\n" + "=" * 40)
        click.echo(f"GitLab URL: {url}")
        click.echo(f"Scan Date: {now.strftime('%Y-%m-%d')}")
        click.echo("-" * 40)
        click.echo(f"Total unique contributors in last {days} days: {total_contributors}")

        if list_contributors:
            click.echo("\n  Contributors:")
            for ident, info in sorted(
                unique_contributors.items(),
                key=lambda x: x[1]["date"],
                reverse=True,
            ):
                commit_url = (
                    f"{url}/{info['project_path']}/-/commit/{info['sha']}"
                )
                display = info["name"] or ident
                email_display = info["email"] or "N/A"
                click.echo(f"    {display:<30} {email_display}")
                click.echo(f"      {commit_url}")
            click.echo()


if __name__ == "__main__":
    main()
