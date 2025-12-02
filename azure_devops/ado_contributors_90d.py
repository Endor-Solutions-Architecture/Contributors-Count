#!/usr/bin/env python3
"""
Azure DevOps Contributors Count Tool

Purpose:
  Calculates the number of unique contributing developers in an Azure DevOps Project
  over the last 90 days.

Requirements:
  Python 3.6+
  Dependencies: requests, click

Installation:
  pip install -r requirements.txt

Usage:
  # Basic usage (requires token)
  export ADO_TOKEN=your_pat
  python ado_contributors_90d.py --org https://dev.azure.com/myorg --project myproject

  # JSON output
  python ado_contributors_90d.py --org https://dev.azure.com/myorg --project myproject --format json

Token Scopes:
  - `Code (Read)`
"""

import os
import sys
import json
import datetime
import time
import base64
from typing import Optional, Dict, Any, Set, Generator

import requests
import click

# Constants
ENV_VAR_TOKEN = "ADO_TOKEN"

class ADOClient:
    def __init__(self, token: str, org_url: str):
        self.token = token
        self.org_url = org_url.rstrip('/')
        self.session = requests.Session()
        
        # ADO uses Basic Auth with PAT. Username is empty string.
        if self.token:
            auth_str = f":{self.token}"
            b64_auth = base64.b64encode(auth_str.encode()).decode()
            self.session.headers.update({"Authorization": f"Basic {b64_auth}"})

    def _request(self, method: str, url: str, params: Dict = None) -> Any:
        while True:
            response = self.session.request(method, url, params=params)
            
            # Handle Rate Limiting (ADO uses 429)
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                click.echo(f"Rate limit exceeded. Sleeping for {retry_after} seconds...", err=True)
                time.sleep(retry_after)
                continue

            if response.status_code != 200:
                try:
                    data = response.json()
                    message = data.get('message', response.text)
                except:
                    message = response.text
                raise Exception(f"ADO API Error ({response.status_code}): {message}")

            return response

    def get_paginated(self, url: str, params: Dict = None) -> Generator[Dict, None, None]:
        if params is None:
            params = {}
        
        # ADO pagination varies. For Git Repos, it's usually all at once or top N.
        # For Commits, it uses skip/top or searchCriteria.
        
        response = self._request('GET', url, params=params)
        data = response.json()
        
        items = data.get('value', [])
        for item in items:
            yield item
            
        # Basic continuation token handling if present (some ADO APIs use 'continuationToken' header)
        # For simplicity in this script, we'll assume standard 'value' list return.
        # If the API requires strict pagination for thousands of repos, we'd need to check 'x-ms-continuationtoken'.

def fetch_repos(client: ADOClient, project: str) -> Generator[Dict, None, None]:
    """Yields repositories for the project."""
    url = f"{client.org_url}/{project}/_apis/git/repositories?api-version=7.1"
    try:
        for repo in client.get_paginated(url):
            yield repo
    except Exception as e:
        raise Exception(f"Failed to fetch repos for project '{project}': {e}")

def fetch_commits(client: ADOClient, repo_id: str, project: str, since: str, until: str) -> Generator[Dict, None, None]:
    """Yields commits for a repository within the time window."""
    url = f"{client.org_url}/{project}/_apis/git/repositories/{repo_id}/commits?api-version=7.1"
    
    # ADO searchCriteria
    params = {
        'searchCriteria.fromDate': since,
        'searchCriteria.toDate': until,
        'searchCriteria.$top': 10000 # Fetch up to 10k commits. Pagination would be needed for more.
    }
    
    try:
        for commit in client.get_paginated(url, params=params):
            yield commit
    except Exception as e:
        click.echo(f"Warning: Failed to fetch commits for repo {repo_id}: {e}", err=True)

@click.command()
@click.option('--org', '-o', required=True, help='Azure DevOps Org URL (e.g. https://dev.azure.com/myorg).')
@click.option('--project', '-p', required=True, help='Project name.')
@click.option('--token', '-t', help='Personal Access Token. Overrides ADO_TOKEN env var.')
@click.option('--format', 'output_format', type=click.Choice(['text', 'json']), default='text', help='Output format.')
@click.option('--list-contributors', is_flag=True, help='List individual contributors and their emails.')
def main(org, project, token, output_format, list_contributors):
    """
    Calculate unique contributors for an Azure DevOps Project over the last 90 days.
    """
    if not token:
        token = os.environ.get(ENV_VAR_TOKEN)

    if not token:
        click.echo("Error: ADO_TOKEN is required.", err=True)
        sys.exit(1)

    client = ADOClient(token, org)

    # Calculate window (90 days)
    now = datetime.datetime.now(datetime.timezone.utc)
    days = 90
    start_date = now - datetime.timedelta(days=days)
    
    since_iso = start_date.isoformat()
    until_iso = now.isoformat()

    contributors_map: Dict[str, Set[str]] = {}
    repo_count = 0
    
    if output_format == 'text':
        click.echo(f"Fetching repositories for {project}...")

    try:
        repos = fetch_repos(client, project)
        
        for repo in repos:
            repo_count += 1
            repo_name = repo['name']
            repo_id = repo['id']
            
            if output_format == 'text':
                click.echo(f"Scanning {repo_name}...", nl=False)
                sys.stdout.flush()

            commits = fetch_commits(client, repo_id, project, since_iso, until_iso)
            
            commit_count = 0
            for commit in commits:
                commit_count += 1
                author = commit.get('author', {})
                email = author.get('email')
                name = author.get('name')
                
                # Use email as unique identifier
                identifier = email if email else name
                
                if identifier:
                    if identifier not in contributors_map:
                        contributors_map[identifier] = set()
                    contributors_map[identifier].add(email)
            
            if output_format == 'text':
                click.echo(f" Done. ({commit_count} commits)")

    except Exception as e:
        click.echo(f"\nError: {e}", err=True)
        sys.exit(1)

    total_contributors = len(contributors_map)

    if output_format == 'json':
        json_output = {
            "org": org,
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
        click.echo(f"Organization: {org}")
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
