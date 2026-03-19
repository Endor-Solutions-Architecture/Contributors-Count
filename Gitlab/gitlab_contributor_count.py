#!/usr/bin/env python3
"""
GitLab Contributors Count Tool

Purpose:
  Calculates the number of unique contributing developers across all accessible
  GitLab groups and projects over a configurable time window (default: 90 days).

Requirements:
  Python 3.6+
  Dependencies: python-gitlab, click

Installation:
  pip install -r requirements.txt

Usage:
  # GitLab.com (SaaS)
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
import datetime
from typing import Dict, Set

import gitlab
import click


DEFAULT_GITLAB_URL = "https://gitlab.com"
ENV_VAR_TOKEN = "GITLAB_TOKEN"


def parse_commit_date(created_at: str) -> datetime.datetime:
    """Parse a GitLab commit timestamp into a datetime object."""
    try:
        return datetime.datetime.fromisoformat(created_at.rstrip('Z'))
    except ValueError:
        return datetime.datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%S.%f%z")


def process_commits(project, since_iso: str, contributors: Dict[str, dict],
                    unique_contributors: Dict[str, dict], gitlab_url: str):
    """Process commits for a project and update contributor maps.

    Uses author_email as the primary dedup key (falls back to author_name).
    Stores the most recent commit info per contributor for reporting.
    """
    commits = project.commits.list(since=since_iso, all=True)
    for commit in commits:
        email = commit.author_email
        name = commit.author_name
        identifier = email if email else name

        if not identifier:
            continue

        commit_date = parse_commit_date(commit.created_at)
        # Use path_with_namespace for correct commit URLs
        project_path = project.path_with_namespace
        commit_info = {
            'name': name,
            'email': email,
            'date': commit_date,
            'sha': commit.id,
            'project_path': project_path,
        }

        if identifier not in contributors or commit_date > contributors[identifier]['date']:
            contributors[identifier] = commit_info

        if identifier not in unique_contributors or commit_date > unique_contributors[identifier]['date']:
            unique_contributors[identifier] = commit_info


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
        click.echo("Error: GITLAB_TOKEN is required. Set it as an environment variable or pass --token.", err=True)
        sys.exit(1)

    gl = gitlab.Gitlab(url, private_token=token)

    now = datetime.datetime.now(datetime.timezone.utc)
    start_date = now - datetime.timedelta(days=days)
    since_iso = start_date.isoformat()

    # group_name -> { identifier -> commit_info }
    all_contributors: Dict[str, Dict[str, dict]] = {}
    # global deduped map: identifier -> commit_info
    unique_contributors: Dict[str, dict] = {}
    # track project IDs already scanned via groups to avoid double-processing
    scanned_project_ids: Set[int] = set()

    # --- Scan group projects ---
    if output_format == 'text':
        click.echo("Fetching groups...")

    for group in gl.groups.list(all=True):
        group_name = group.name
        if output_format == 'text':
            click.echo(f"\nAnalyzing group: {group_name}")

        contributors: Dict[str, dict] = {}

        for group_project in group.projects.list(all=True):
            project = gl.projects.get(group_project.id)
            scanned_project_ids.add(project.id)
            if output_format == 'text':
                click.echo(f"  Scanning project: {project.name}...", nl=False)
                sys.stdout.flush()

            process_commits(project, since_iso, contributors, unique_contributors, url)

            if output_format == 'text':
                click.echo(" Done.")

        all_contributors[group_name] = contributors

    # --- Scan standalone / membership projects not already covered by groups ---
    if output_format == 'text':
        click.echo("\nAnalyzing standalone/membership projects:")

    standalone_contributors: Dict[str, dict] = {}
    for project in gl.projects.list(membership=True, all=True):
        if project.id in scanned_project_ids:
            continue
        scanned_project_ids.add(project.id)

        if output_format == 'text':
            click.echo(f"  Scanning project: {project.name}...", nl=False)
            sys.stdout.flush()

        process_commits(project, since_iso, standalone_contributors, unique_contributors, url)

        if output_format == 'text':
            click.echo(" Done.")

    all_contributors["Standalone Projects"] = standalone_contributors

    # --- Output ---
    total_contributors = len(unique_contributors)

    if output_format == 'json':
        json_output = {
            "gitlab_url": url,
            "scan_date": now.strftime('%Y-%m-%d'),
            "days": days,
            "unique_contributors": total_contributors,
            "groups": {}
        }

        for group_name, contributors in all_contributors.items():
            json_output["groups"][group_name] = {
                "unique_contributors": len(contributors)
            }

        if list_contributors:
            json_output["contributors_details"] = [
                {
                    "identifier": ident,
                    "name": info['name'],
                    "email": info.get('email', ''),
                    "last_commit_date": info['date'].strftime('%Y-%m-%d %H:%M:%S'),
                    "last_commit_url": f"{url}/{info['project_path']}/-/commit/{info['sha']}"
                }
                for ident, info in sorted(unique_contributors.items())
            ]

        click.echo(json.dumps(json_output, indent=2))
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
            click.echo("-" * 40)
            click.echo("All contributors:")
            for ident, info in sorted(unique_contributors.items(), key=lambda x: x[1]['date'], reverse=True):
                commit_url = f"{url}/{info['project_path']}/-/commit/{info['sha']}"
                click.echo(f"  - {info['name']} ({info.get('email', 'N/A')}): "
                           f"{info['date'].strftime('%Y-%m-%d %H:%M:%S')} UTC")
                click.echo(f"    Commit: {commit_url}")

        click.echo("=" * 40)


if __name__ == '__main__':
    main()
