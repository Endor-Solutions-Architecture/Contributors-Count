import click
import json
from datetime import datetime, timedelta

from .config import Config, ConfigLoader
from .providers.factory import ProviderFactory
from .counter import ContributorCounter

@click.command()
@click.option('--config', type=click.Path(exists=True), required=True,
              help='Path to YAML configuration file')
@click.option('--token', required=True, envvar='GIT_TOKEN',
              help='Authentication token (can be set via GIT_TOKEN env var)')
@click.option('--explain', is_flag=True, default=False,
              help='Generate a detailed report (output.json)')
@click.option('--days', type=int, required=False, default=90,
              help='Number of days to search (default: 90)')
def cli(config: str, token: str, explain: bool, days: int) -> None:
    """Count contributors in an organization."""

    # Load configuration
    config_obj: Config = ConfigLoader.load(config)
    #print(config_obj)

    # Initialize provider
    git_provider = ProviderFactory.create_provider(
        config_obj.provider.type,
        token,
        config_obj.provider.url
    )
    
    # Set up counter
    counter = ContributorCounter(git_provider, config_obj)
    
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # Count contributors
    contributors, repositories, excluded_contributors, excluded_repositories = counter.count_contributors(start_date, end_date)
    
    # Print summary
    click.echo(f"\nGit Contributor Report")
    click.echo(f"Organization: {config_obj.provider.org}")
    click.echo(f"Period: {start_date.date()} - {end_date.date()}\n")
    click.echo(f"Total Contributors: {len(contributors)}")
    click.echo(f"Total Repositories: {len(repositories)}")
    if len(excluded_contributors) > 0:
        click.echo(f"Total Excluded Contributors: {len(excluded_contributors)}")
    if len(excluded_repositories) > 0:
        click.echo(f"Total Excluded Repositories: {len(excluded_repositories)}")

    if explain:
        report = {
            'metadata': {
                'organization': config_obj.provider.org,
                'provider': config_obj.provider.type,
                'url': config_obj.provider.url,
                'period': {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat()
                }
            },
            'summary': {
                'total_contributors': len(contributors),
                'total_repositories': len(repositories),
                'excluded_contributors': len(excluded_contributors),
                'excluded_repositories': len(excluded_repositories)
            },
            'contributors': {
                username: {
                    'commit_count': stats.commit_count,
                    'first_commit': stats.first_commit.isoformat(),
                    'last_commit': stats.last_commit.isoformat(),
                    'repositories': stats.repositories
                }
                for username, stats in contributors.items()
            },
            'repositories': {
                name: {
                    'contributor_count': stats.contributor_count,
                    'commit_count': stats.commit_count,
                    'contributors': stats.contributors
                }
                for name, stats in repositories.items()
            },
            'excluded-contributors': list(excluded_contributors),
            'excluded-repositories': list(excluded_repositories)
        }
    
        # Save report
        output = "output.json"
        with open(output, 'w') as f:
            json.dump(report, f, indent=2)
        click.echo(f"\nDetailed report written to {output}")
    
    # Cleanup
    git_provider.close()
