#!/usr/bin/env python3
"""
GitHub Contributors Count Tool

Purpose:
  Calculates the number of unique contributing developers in a GitHub organization
  over the last 90 days.

Requirements:
  Python 3.6+
  Dependencies: requests, click

Installation:
  pip install -r requirements.txt

Usage:
  # Public org, no token (subject to lower rate limits)
  python github_contributors_90d.py --org my-org

  # Private org or higher rate limits (recommended)
  export GITHUB_TOKEN=ghp_...
  python github_contributors_90d.py --org my-org

  # JSON output
  python github_contributors_90d.py --org my-org --format json

Token Scopes:
  - Public orgs: No scopes needed (or just public_repo).
  - Private orgs: `read:org` and `repo` (read-only) scopes.
"""

import os
import sys
import json
import datetime
import time
from typing import Optional, Dict, Any, Set, Generator, List

import requests
import click

# Constants
DEFAULT_BASE_URL = "https://api.github.com"
ENV_VAR_TOKEN = "GITHUB_TOKEN"

class GitHubClient:
    def __init__(self, token: Optional[str], base_url: str = DEFAULT_BASE_URL):
        self.token = token
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({"Authorization": f"token {self.token}"})
        self.session.headers.update({"Accept": "application/vnd.github.v3+json"})

    def _request(self, method: str, endpoint: str, params: Dict = None) -> Any:
        url = f"{self.base_url}{endpoint}"
        while True:
            response = self.session.request(method, url, params=params)
            
            # Handle Rate Limiting
            if response.status_code == 403 and 'X-RateLimit-Remaining' in response.headers:
                remaining = int(response.headers.get('X-RateLimit-Remaining', 0))
                if remaining == 0:
                    reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                    sleep_seconds = max(0, reset_time - int(time.time())) + 1
                    click.echo(f"Rate limit exceeded. Sleeping for {sleep_seconds} seconds...", err=True)
                    time.sleep(sleep_seconds)
                    continue

            if response.status_code != 200:
                # Try to get error message
                try:
                    data = response.json()
                    message = data.get('message', response.text)
                except:
                    message = response.text
                raise Exception(f"GitHub API Error ({response.status_code}): {message}")

            return response

    def get_paginated(self, endpoint: str, params: Dict = None) -> Generator[Dict, None, None]:
        if params is None:
            params = {}
        params['per_page'] = 100
        
        url = f"{self.base_url}{endpoint}"
        
        while url:
            response = self._request('GET', url.replace(self.base_url, ''), params=params)
            
            items = response.json()
            if not isinstance(items, list):
                # Some endpoints return a dict, but for lists we expect a list
                yield items
                return

            for item in items:
                yield item
            
            # Handle pagination links
            if 'next' in response.links:
                url = response.links['next']['url']
                params = {} # Params are usually encoded in the next link
            else:
                url = None

def fetch_repos(client: GitHubClient, org: str, max_repos: Optional[int] = None) -> Generator[Dict, None, None]:
    """Yields repositories for the organization."""
    count = 0
    try:
        # Try fetching org repos
        for repo in client.get_paginated(f"/orgs/{org}/repos"):
            yield repo
            count += 1
            if max_repos and count >= max_repos:
                break
    except Exception as e:
        raise Exception(f"Failed to fetch repos for org '{org}': {e}")

def fetch_commits(client: GitHubClient, repo_full_name: str, since: str, until: str) -> Generator[Dict, None, None]:
    """Yields commits for a repository within the time window."""
    params = {'since': since, 'until': until}
    try:
        for commit in client.get_paginated(f"/repos/{repo_full_name}/commits", params=params):
            yield commit
    except Exception as e:
        # If a repo is empty or other issue, just log to stderr and continue
        click.echo(f"Warning: Failed to fetch commits for {repo_full_name}: {e}", err=True)

@click.command()
@click.option('--org', '-o', required=True, help='GitHub organization name.')
@click.option('--token', '-t', help='GitHub Personal Access Token. Overrides GITHUB_TOKEN env var.')
@click.option('--base-url', default=DEFAULT_BASE_URL, help='GitHub API Base URL.')
@click.option('--format', 'output_format', type=click.Choice(['text', 'json']), default='text', help='Output format.')
@click.option('--max-repos', type=int, help='Limit the number of repositories to process (for testing/large orgs).')
@click.option('--list-contributors', is_flag=True, help='List individual contributors and their emails.')
def main(org, token, base_url, output_format, max_repos, list_contributors):
    """
    Calculate unique contributors for a GitHub Org over the last 90 days.
    """
    # Resolve token
    if not token:
        token = os.environ.get(ENV_VAR_TOKEN)

    if not token and output_format == 'text':
        click.echo("Note: No token provided. Using anonymous access (lower rate limits).", err=True)

    client = GitHubClient(token, base_url)

    # Calculate window (90 days)
    now = datetime.datetime.now(datetime.timezone.utc)
    days = 90
    start_date = now - datetime.timedelta(days=days)
    
    # ISO 8601 format for GitHub API
    since_iso = start_date.isoformat()
    until_iso = now.isoformat()

    # Map login -> Set of emails
    contributors_map: Dict[str, Set[str]] = {}
    repo_count = 0
    
    if output_format == 'text':
        click.echo(f"Fetching repositories for {org}...")

    try:
        repos = fetch_repos(client, org, max_repos)
        
        for repo in repos:
            repo_count += 1
            repo_name = repo['full_name']
            if output_format == 'text':
                click.echo(f"Scanning {repo_name}...", nl=False)
                sys.stdout.flush()

            commits = fetch_commits(client, repo_name, since_iso, until_iso)
            
            commit_count = 0
            for commit in commits:
                commit_count += 1
                author = commit.get('author')
                commit_author_info = commit.get('commit', {}).get('author', {})
                
                if author and 'login' in author:
                    login = author['login']
                    email = commit_author_info.get('email')
                    
                    if login not in contributors_map:
                        contributors_map[login] = set()
                    
                    if email:
                        contributors_map[login].add(email)
            
            if output_format == 'text':
                click.echo(f" Done. ({commit_count} commits fetched)")

    except Exception as e:
        click.echo(f"\nError: {e}", err=True)
        sys.exit(1)

    total_contributors = len(contributors_map)

    if output_format == 'json':
        json_output = {
            "org": org,
            "scan_date": now.strftime('%Y-%m-%d'),
            "contributors_90d": total_contributors
        }
        
        if list_contributors:
            json_output["contributors_details"] = [
                {"login": login, "emails": sorted(list(emails))}
                for login, emails in sorted(contributors_map.items())
            ]
            
        click.echo(json.dumps(json_output, indent=2))
    else:
        click.echo("\n" + "="*40)
        click.echo(f"Organization: {org}")
        click.echo(f"Scan Date: {now.strftime('%Y-%m-%d')}")
        click.echo(f"Repositories scanned: {repo_count}")
        click.echo("-" * 40)
        click.echo(f"Contributors in last 90 days: {total_contributors}")
        
        if list_contributors:
            click.echo("-" * 40)
            click.echo("Contributors:")
            for login in sorted(contributors_map.keys()):
                emails = ", ".join(sorted(contributors_map[login]))
                click.echo(f"  - {login} ({emails})")
                
        click.echo("="*40)

if __name__ == '__main__':
    main()
