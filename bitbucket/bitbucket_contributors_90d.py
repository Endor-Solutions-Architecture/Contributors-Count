#!/usr/bin/env python3
"""
Bitbucket Contributors Count Tool

Purpose:
  Calculates the number of unique contributing developers in a Bitbucket Workspace
  over the last 90 days.

Requirements:
  Python 3.6+
  Dependencies: requests, click

Installation:
  pip install -r requirements.txt

Usage:
  # Basic usage (requires App Password)
  export BITBUCKET_USER=myuser
  export BITBUCKET_PASSWORD=my_app_password
  python bitbucket_contributors_90d.py --workspace myworkspace

  # JSON output
  python bitbucket_contributors_90d.py --workspace myworkspace --format json

Token Scopes:
  - `Repositories: Read`
"""

import os
import sys
import json
import datetime
import time
from typing import Optional, Dict, Any, Set, Generator

import requests
import click

# Constants
DEFAULT_BASE_URL = "https://api.bitbucket.org/2.0"
ENV_VAR_USER = "BITBUCKET_USER"
ENV_VAR_PASSWORD = "BITBUCKET_PASSWORD"

class BitbucketClient:
    def __init__(self, user: str, password: str, base_url: str = DEFAULT_BASE_URL):
        self.user = user
        self.password = password
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        
        if self.user and self.password:
            self.session.auth = (self.user, self.password)

    def _request(self, method: str, url: str, params: Dict = None) -> Any:
        while True:
            response = self.session.request(method, url, params=params)
            
            # Handle Rate Limiting
            if response.status_code == 429:
                # Bitbucket usually sends 'Retry-After'
                retry_after = int(response.headers.get('Retry-After', 60))
                click.echo(f"Rate limit exceeded. Sleeping for {retry_after} seconds...", err=True)
                time.sleep(retry_after)
                continue

            if response.status_code != 200:
                try:
                    data = response.json()
                    message = data.get('error', {}).get('message', response.text)
                except:
                    message = response.text
                raise Exception(f"Bitbucket API Error ({response.status_code}): {message}")

            return response

    def get_paginated(self, url: str, params: Dict = None) -> Generator[Dict, None, None]:
        if params is None:
            params = {}
        
        # Bitbucket pagination uses 'next' link in response
        while url:
            response = self._request('GET', url, params=params)
            data = response.json()
            
            items = data.get('values', [])
            for item in items:
                yield item
            
            url = data.get('next')
            params = {} # Params are encoded in next link

def fetch_repos(client: BitbucketClient, workspace: str) -> Generator[Dict, None, None]:
    """Yields repositories for the workspace."""
    url = f"{client.base_url}/repositories/{workspace}"
    try:
        for repo in client.get_paginated(url):
            yield repo
    except Exception as e:
        raise Exception(f"Failed to fetch repos for workspace '{workspace}': {e}")

def fetch_commits(client: BitbucketClient, workspace: str, repo_slug: str, since_iso: str) -> Generator[Dict, None, None]:
    """Yields commits for a repository since a date."""
    # Bitbucket API doesn't have a simple 'since' param for commits endpoint in the same way.
    # It supports `?q=date > ...` filtering if using 2.0 API properly, but sometimes it's tricky.
    # Alternatively, we iterate until we hit a date older than 'since'.
    # Let's try to use the `q` parameter which is powerful in Bitbucket API 2.0.
    # Format: date > "2021-01-01T00:00:00+00:00"
    
    url = f"{client.base_url}/repositories/{workspace}/{repo_slug}/commits"
    query = f'date > "{since_iso}"'
    params = {'q': query}
    
    try:
        for commit in client.get_paginated(url, params=params):
            yield commit
    except Exception as e:
        click.echo(f"Warning: Failed to fetch commits for repo {repo_slug}: {e}", err=True)

@click.command()
@click.option('--workspace', '-w', required=True, help='Bitbucket Workspace ID/Slug.')
@click.option('--user', '-u', help='Bitbucket Username. Overrides BITBUCKET_USER env var.')
@click.option('--password', '-p', help='Bitbucket App Password. Overrides BITBUCKET_PASSWORD env var.')
@click.option('--format', 'output_format', type=click.Choice(['text', 'json']), default='text', help='Output format.')
@click.option('--list-contributors', is_flag=True, help='List individual contributors and their emails.')
def main(workspace, user, password, output_format, list_contributors):
    """
    Calculate unique contributors for a Bitbucket Workspace over the last 90 days.
    """
    if not user:
        user = os.environ.get(ENV_VAR_USER)
    if not password:
        password = os.environ.get(ENV_VAR_PASSWORD)

    if not user or not password:
        click.echo("Error: BITBUCKET_USER and BITBUCKET_PASSWORD are required.", err=True)
        sys.exit(1)

    client = BitbucketClient(user, password)

    # Calculate window (90 days)
    now = datetime.datetime.now(datetime.timezone.utc)
    days = 90
    start_date = now - datetime.timedelta(days=days)
    
    since_iso = start_date.isoformat()

    contributors_map: Dict[str, Set[str]] = {}
    repo_count = 0
    
    if output_format == 'text':
        click.echo(f"Fetching repositories for {workspace}...")

    try:
        repos = fetch_repos(client, workspace)
        
        for repo in repos:
            repo_count += 1
            repo_name = repo['name']
            repo_slug = repo['slug']
            
            if output_format == 'text':
                click.echo(f"Scanning {repo_name}...", nl=False)
                sys.stdout.flush()

            commits = fetch_commits(client, workspace, repo_slug, since_iso)
            
            commit_count = 0
            for commit in commits:
                commit_count += 1
                author = commit.get('author', {})
                raw = author.get('raw') # "Name <email>"
                user_info = author.get('user', {})
                
                # Bitbucket author object:
                # 'raw': 'Name <email>'
                # 'user': { 'display_name': ..., 'uuid': ..., 'account_id': ... } (if mapped)
                
                # We want unique developers.
                # If 'user' object exists, 'account_id' is best.
                # If not, parse email from 'raw'.
                
                identifier = None
                email = None
                
                if 'account_id' in user_info:
                    identifier = user_info['account_id']
                elif raw:
                    # Simple parse for email
                    if '<' in raw and '>' in raw:
                        email = raw.split('<')[-1].strip('>')
                        identifier = email
                    else:
                        identifier = raw
                
                if identifier:
                    if identifier not in contributors_map:
                        contributors_map[identifier] = set()
                    if email:
                        contributors_map[identifier].add(email)
            
            if output_format == 'text':
                click.echo(f" Done. ({commit_count} commits)")

    except Exception as e:
        click.echo(f"\nError: {e}", err=True)
        sys.exit(1)

    total_contributors = len(contributors_map)

    if output_format == 'json':
        json_output = {
            "workspace": workspace,
            "scan_date": now.strftime('%Y-%m-%d'),
            "contributors_90d": total_contributors
        }
        
        if list_contributors:
            json_output["contributors_details"] = [
                {"identifier": ident, "emails": sorted(list(emails))}
                for ident, emails in sorted(contributors_map.items())
            ]
            
        click.echo(json.dumps(json_output, indent=2))
    else:
        click.echo("\n" + "="*40)
        click.echo(f"Workspace: {workspace}")
        click.echo(f"Scan Date: {now.strftime('%Y-%m-%d')}")
        click.echo(f"Repositories scanned: {repo_count}")
        click.echo("-" * 40)
        click.echo(f"Contributors in last 90 days: {total_contributors}")
        
        if list_contributors:
            click.echo("-" * 40)
            click.echo("Contributors:")
            for ident in sorted(contributors_map.keys()):
                emails = ", ".join(sorted(contributors_map[ident]))
                click.echo(f"  - {ident} ({emails})")
                
        click.echo("="*40)

if __name__ == '__main__':
    main()
