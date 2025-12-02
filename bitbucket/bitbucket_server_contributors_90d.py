#!/usr/bin/env python3
"""
Bitbucket Server (Data Center) Contributors Count Tool

Purpose:
  Calculates the number of unique contributing developers in a Bitbucket Server Project
  over the last 90 days.

Requirements:
  Python 3.6+
  Dependencies: requests, click

Installation:
  pip install -r requirements.txt

Usage:
  # Basic usage (requires credentials)
  export BITBUCKET_SERVER_URL=https://bitbucket.mycompany.com
  export BITBUCKET_USER=myuser
  export BITBUCKET_PASSWORD=mypassword
  python bitbucket_server_contributors_90d.py --project MYPROJ

  # JSON output
  python bitbucket_server_contributors_90d.py --project MYPROJ --format json

Token Scopes:
  - Project/Repo Read permissions
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
ENV_VAR_URL = "BITBUCKET_SERVER_URL"
ENV_VAR_USER = "BITBUCKET_USER"
ENV_VAR_PASSWORD = "BITBUCKET_PASSWORD"

class BitbucketServerClient:
    def __init__(self, base_url: str, user: str, password: str):
        self.base_url = base_url.rstrip('/')
        self.user = user
        self.password = password
        self.session = requests.Session()
        
        if self.user and self.password:
            self.session.auth = (self.user, self.password)

    def _request(self, method: str, endpoint: str, params: Dict = None) -> Any:
        url = f"{self.base_url}{endpoint}"
        while True:
            response = self.session.request(method, url, params=params)
            
            # Handle Rate Limiting (if applicable, usually less common on-prem)
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                click.echo(f"Rate limit exceeded. Sleeping for {retry_after} seconds...", err=True)
                time.sleep(retry_after)
                continue

            if response.status_code != 200:
                try:
                    data = response.json()
                    message = data.get('errors', [{}])[0].get('message', response.text)
                except:
                    message = response.text
                raise Exception(f"Bitbucket Server API Error ({response.status_code}): {message}")

            return response

    def get_paginated(self, endpoint: str, params: Dict = None) -> Generator[Dict, None, None]:
        if params is None:
            params = {}
        
        # Bitbucket Server pagination uses 'start' (offset) and 'limit'
        # Response contains 'isLastPage', 'nextPageStart', 'values'
        
        start = 0
        limit = 100 # Default limit
        params['limit'] = limit
        
        while True:
            params['start'] = start
            response = self._request('GET', endpoint, params=params)
            data = response.json()
            
            items = data.get('values', [])
            for item in items:
                yield item
            
            if data.get('isLastPage', True):
                break
            
            next_start = data.get('nextPageStart')
            if next_start:
                start = next_start
            else:
                # Fallback if nextPageStart is missing but isLastPage is false
                start += len(items)

def fetch_repos(client: BitbucketServerClient, project_key: str) -> Generator[Dict, None, None]:
    """Yields repositories for the project."""
    try:
        for repo in client.get_paginated(f"/rest/api/1.0/projects/{project_key}/repos"):
            yield repo
    except Exception as e:
        raise Exception(f"Failed to fetch repos for project '{project_key}': {e}")

def fetch_commits(client: BitbucketServerClient, project_key: str, repo_slug: str, since_timestamp_ms: int) -> Generator[Dict, None, None]:
    """Yields commits for a repository since a timestamp (ms)."""
    # Bitbucket Server commits API doesn't strictly support 'since' date filtering in the base endpoint easily
    # without iterating. However, we can iterate until we hit a commit older than the date.
    # Commits are returned in reverse chronological order by default.
    
    endpoint = f"/rest/api/1.0/projects/{project_key}/repos/{repo_slug}/commits"
    
    try:
        # We need to manually handle pagination here to stop early
        start = 0
        limit = 100
        
        while True:
            params = {'start': start, 'limit': limit}
            response = client._request('GET', endpoint, params=params)
            data = response.json()
            
            items = data.get('values', [])
            if not items:
                break
                
            for commit in items:
                commit_ts = commit.get('authorTimestamp', 0)
                if commit_ts < since_timestamp_ms:
                    return # Stop iterating, we reached older commits
                yield commit
            
            if data.get('isLastPage', True):
                break
            
            next_start = data.get('nextPageStart')
            if next_start:
                start = next_start
            else:
                start += len(items)
                
    except Exception as e:
        click.echo(f"Warning: Failed to fetch commits for repo {repo_slug}: {e}", err=True)

@click.command()
@click.option('--project', '-p', required=True, help='Bitbucket Project Key.')
@click.option('--url', required=True, help='Bitbucket Server Base URL (e.g. https://bitbucket.mycompany.com).')
@click.option('--user', '-u', help='Username. Overrides BITBUCKET_USER env var.')
@click.option('--password', '-pw', help='Password/Token. Overrides BITBUCKET_PASSWORD env var.')
@click.option('--format', 'output_format', type=click.Choice(['text', 'json']), default='text', help='Output format.')
@click.option('--list-contributors', is_flag=True, help='List individual contributors and their emails.')
def main(project, url, user, password, output_format, list_contributors):
    """
    Calculate unique contributors for a Bitbucket Server Project over the last 90 days.
    """
    if not user:
        user = os.environ.get(ENV_VAR_USER)
    if not password:
        password = os.environ.get(ENV_VAR_PASSWORD)

    if not user or not password:
        click.echo("Error: BITBUCKET_USER and BITBUCKET_PASSWORD are required.", err=True)
        sys.exit(1)

    client = BitbucketServerClient(url, user, password)

    # Calculate window (90 days)
    now = datetime.datetime.now(datetime.timezone.utc)
    days = 90
    start_date = now - datetime.timedelta(days=days)
    
    # Bitbucket Server uses milliseconds timestamp
    since_timestamp_ms = int(start_date.timestamp() * 1000)

    contributors_map: Dict[str, Set[str]] = {}
    repo_count = 0
    
    if output_format == 'text':
        click.echo(f"Fetching repositories for {project}...")

    try:
        repos = fetch_repos(client, project)
        
        for repo in repos:
            repo_count += 1
            repo_name = repo['name']
            repo_slug = repo['slug']
            
            if output_format == 'text':
                click.echo(f"Scanning {repo_name}...", nl=False)
                sys.stdout.flush()

            commits = fetch_commits(client, project, repo_slug, since_timestamp_ms)
            
            commit_count = 0
            for commit in commits:
                commit_count += 1
                author = commit.get('author', {})
                email = author.get('emailAddress')
                name = author.get('name')
                
                # Use email as unique identifier
                identifier = email if email else name
                
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
            "project": project,
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
        click.echo(f"Project: {project}")
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
