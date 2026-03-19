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

  # Markdown output
  python gitlab_contributor_count.py --format markdown

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
# Bot detection
# ---------------------------------------------------------------------------

_BOT_SUFFIXES = ("[bot]",)
_BOT_NAME_KEYWORDS = (
    "build service", "dependabot", "renovate", "snyk", "codecov",
    "greenkeeper", "mergify", "project_bot",
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
# Core logic
# ---------------------------------------------------------------------------

def _process_project(
    gl_client: gitlab.Gitlab,
    project_id: int,
    since_iso: str,
    contributors: Dict[str, dict],
    unique_contributors: Dict[str, dict],
    gitlab_url: str,
    exclude_bots: bool = False,
    skipped_projects: Optional[List[str]] = None,
) -> Tuple[int, int]:
    """Process commits for a single project and update contributor maps.

    Uses author_email as the primary dedup key (falls back to author_name).
    Returns (commit_count, bots_filtered).
    """
    try:
        project = gl_client.projects.get(project_id)
    except gitlab.exceptions.GitlabGetError as exc:
        click.echo(
            f"  Warning: could not access project {project_id} "
            f"({exc.response_code})",
            err=True,
        )
        if skipped_projects is not None:
            skipped_projects.append(f"project:{project_id}")
        return (0, 0)

    project_path: str = project.path_with_namespace

    try:
        commits = project.commits.list(since=since_iso, all=True)
    except gitlab.exceptions.GitlabListError as exc:
        click.echo(
            f"  Warning: could not list commits for {project_path} "
            f"({exc.response_code})",
            err=True,
        )
        if skipped_projects is not None:
            skipped_projects.append(project_path)
        return (0, 0)

    commit_count = 0
    bots_filtered = 0
    for commit in commits:
        commit_count += 1
        email: Optional[str] = getattr(commit, "author_email", None)
        name: Optional[str] = getattr(commit, "author_name", None)

        if exclude_bots and _is_bot(name or "", email):
            bots_filtered += 1
            continue

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

    return (commit_count, bots_filtered)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option('--url', '-u', default=DEFAULT_GITLAB_URL,
              help='GitLab instance URL (default: https://gitlab.com).')
@click.option('--token', '-t', help='GitLab Personal Access Token. Overrides GITLAB_TOKEN env var.')
@click.option('--format', 'output_format', type=click.Choice(['text', 'json', 'markdown']), default='text',
              help='Output format.')
@click.option('--list-contributors', is_flag=True, help='List individual contributors and their emails.')
@click.option('--days', '-d', type=int, default=90, show_default=True, help='Number of days to look back for contributions.')
@click.option('--exclude-bots', is_flag=True, help='Exclude bot/service accounts from the contributor count.')
@click.option('--verbose', '-v', is_flag=True, help='Print API diagnostics to stderr.')
def main(url, token, output_format, list_contributors, days, exclude_bots, verbose):
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

    def vlog(msg: str) -> None:
        if verbose:
            click.echo(f"  [verbose] {msg}", err=True)

    # python-gitlab handles retries and timeouts natively
    gl = gitlab.Gitlab(
        url,
        private_token=token,
        timeout=REQUEST_TIMEOUT,
        retry_transient_errors=True,
        user_agent="contributors-count/1.0",
    )

    vlog(f"GitLab URL: {url}")
    vlog(f"Time window: last {days} days")

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
    skipped_projects: List[str] = []
    total_commits = 0
    bots_filtered = 0
    group_project_counts: Dict[str, int] = {}

    # -- Scan group projects -------------------------------------------------
    if output_format == "text":
        click.echo("Fetching groups ...")

    try:
        groups = gl.groups.list(all=True)
    except gitlab.exceptions.GitlabListError as exc:
        click.echo(f"Error listing groups: {exc}", err=True)
        sys.exit(1)

    vlog(f"Fetched {len(groups)} groups")

    for group in groups:
        group_name: str = group.name
        if output_format == "text":
            click.echo(f"\n  Group: {group_name}")

        contributors: Dict[str, dict] = {}
        group_proj_count = 0

        try:
            group_projects = group.projects.list(all=True)
        except gitlab.exceptions.GitlabListError:
            click.echo(
                f"  Warning: could not list projects in {group_name}",
                err=True,
            )
            all_contributors[group_name] = contributors
            group_project_counts[group_name] = 0
            continue

        for gp in group_projects:
            scanned_project_ids.add(gp.id)
            group_proj_count += 1
            if output_format == "text":
                click.echo(f"    {gp.name} ...", nl=False)
                sys.stdout.flush()

            t_proj = time.monotonic()
            cc, bf = _process_project(
                gl, gp.id, since_iso,
                contributors, unique_contributors, url,
                exclude_bots=exclude_bots,
                skipped_projects=skipped_projects,
            )
            total_commits += cc
            bots_filtered += bf

            vlog(f"{gp.name}: {cc:,} commits in {_elapsed(time.monotonic() - t_proj)}")

            if output_format == "text":
                click.echo(f" {cc:,} commits")

        all_contributors[group_name] = contributors
        group_project_counts[group_name] = group_proj_count

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

    standalone_count = 0
    for project in membership_projects:
        if project.id in scanned_project_ids:
            continue
        scanned_project_ids.add(project.id)
        standalone_count += 1

        if output_format == "text":
            click.echo(f"    {project.name} ...", nl=False)
            sys.stdout.flush()

        t_proj = time.monotonic()
        cc, bf = _process_project(
            gl, project.id, since_iso,
            standalone_contributors, unique_contributors, url,
            exclude_bots=exclude_bots,
            skipped_projects=skipped_projects,
        )
        total_commits += cc
        bots_filtered += bf

        vlog(f"{project.name}: {cc:,} commits in {_elapsed(time.monotonic() - t_proj)}")

        if output_format == "text":
            click.echo(f" {cc:,} commits")

    all_contributors["Standalone Projects"] = standalone_contributors
    group_project_counts["Standalone Projects"] = standalone_count

    elapsed = time.monotonic() - t0
    total_contributors = len(unique_contributors)
    total_projects = len(scanned_project_ids)

    # -- Output --------------------------------------------------------------
    if output_format == "json":
        payload = {
            "gitlab_url": url,
            "scan_date": now.strftime('%Y-%m-%d'),
            "days": days,
            "exclude_bots": exclude_bots,
            "unique_contributors": total_contributors,
            "skipped_projects": skipped_projects,
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
    elif output_format == "markdown":
        click.echo("# Contributors Report — GitLab")
        click.echo()
        click.echo("| Field | Value |")
        click.echo("|-------|-------|")
        click.echo(f"| GitLab URL | {url} |")
        click.echo(f"| Scan Date | {now.strftime('%Y-%m-%d')} |")
        click.echo(f"| Days | {days} |")
        click.echo(f"| Groups Scanned | {len(groups)} |")
        click.echo(f"| Bots Excluded | {'Yes' if exclude_bots else 'No'} |")
        click.echo(f"| Total Unique Contributors | {total_contributors} |")
        click.echo()

        for group_name, contributors in all_contributors.items():
            proj_count = group_project_counts.get(group_name, 0)
            click.echo(f"<details>")
            click.echo(f"<summary><strong>{group_name}</strong> — {len(contributors)} contributors, {proj_count} projects</summary>")
            click.echo()
            if list_contributors:
                for ident, info in sorted(contributors.items(), key=lambda x: x[1]['date'], reverse=True):
                    commit_url = f"{url}/{info['project_path']}/-/commit/{info['sha']}"
                    click.echo(f"- **{info['name'] or ident}** ({info.get('email', 'N/A')}) — {info['date'].strftime('%Y-%m-%d %H:%M:%S')} UTC")
                    click.echo(f"  - [Commit]({commit_url})")
                click.echo()
            else:
                click.echo(f"Contributors: {', '.join(sorted(info['name'] or ident for ident, info in contributors.items()))}")
                click.echo()
            click.echo("</details>")
            click.echo()

        if list_contributors:
            click.echo("## All Contributors")
            click.echo()
            for ident, info in sorted(
                unique_contributors.items(),
                key=lambda x: x[1]["date"],
                reverse=True,
            ):
                commit_url = f"{url}/{info['project_path']}/-/commit/{info['sha']}"
                display = info["name"] or ident
                click.echo(f"- **{display}** ({info['email'] or 'N/A'}) — [Commit]({commit_url})")
            click.echo()

        if skipped_projects:
            click.echo("## Skipped Projects")
            click.echo()
            for p in skipped_projects:
                click.echo(f"- {p}")
            click.echo()

        click.echo("---")
        click.echo(f"*Report generated by gitlab_contributor_count.py on {now.strftime('%Y-%m-%d %H:%M:%S')} UTC*")
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
        if exclude_bots:
            click.echo(f"Bots excluded: Yes ({bots_filtered:,} bot commits filtered)")

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
