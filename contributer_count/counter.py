import logging
from datetime import datetime
from typing import Dict, Optional, Tuple, List
from .config import Config
from .filters import FilterManager
from .models import ContributorStats, RepoStats
from .providers.base import GitProvider

logger = logging.getLogger(__name__)
logging.basicConfig(
    filename='last_run.log',
    filemode="w",
    format='%(asctime)s %(message)s',
    encoding='utf-8',
    level=logging.DEBUG
)

class ContributorCounter:
    """Main class for counting contributors across repositories."""
    
    def __init__(self, provider: GitProvider, config: Config):
        """
        Initialize the counter with a Git provider and configuration.
        
        Args:
            provider: An implementation of GitProvider for accessing repositories
            config: Configuration object containing filtering rules and settings
        """
        self.provider = provider
        self.org = config.provider.org
        self.filter_manager = FilterManager(config)

    def count_contributors(
        self,
        start_date: datetime,
        end_date: Optional[datetime] = None
    ) -> Tuple[Dict[str, ContributorStats], Dict[str, RepoStats], set, set]:
        """
        Count contributors and generate statistics for an organization.
        
        Args:
            start_date: Start date for contribution window
            end_date: Optional end date for contribution window
        
        Returns:
            Tuple of (contributor_stats, repository_stats)
        """
        contributors: Dict[str, ContributorStats] = {}
        repositories: Dict[str, RepoStats] = {}
        excluded_contributers = set()
        excluded_repositories = set()

        
        try:
            repos = list(self.provider.get_organization_repos(self.org))
            logger.info(f"Found {len(repos)} repositories in organization {self.org}")
            
            for repo in repos:
                if not self.filter_manager.should_include_repo(repo.name):
                    excluded_repositories.add(repo.name)
                    logger.debug(f"Skipping excluded repository: {repo.name}")
                    continue
                
                logger.info(f"Processing repository: {repo.full_name}")
                self._process_repository(
                    repo.full_name,
                    start_date,
                    end_date,
                    contributors,
                    repositories,
                    excluded_contributers
                )
                
        except Exception as e:
            logger.error(f"Error processing organization {self.org}: {str(e)}")
            raise
        
        return contributors, repositories, excluded_contributers, excluded_repositories

    def _process_repository(
        self,
        repo_full_name: str,
        start_date: datetime,
        end_date: Optional[datetime],
        contributors: Dict[str, ContributorStats],
        repositories: Dict[str, RepoStats],
        excluded_contributors: set
    ) -> None:
        """
        Process a single repository and update statistics.
        
        Args:
            repo_full_name: Full name of the repository
            start_date: Start date for contribution window
            end_date: Optional end date for contribution window
            contributors: Dictionary of contributor statistics to update
            repo_stats: Dictionary of repository statistics to update
        """
        repo_contributors = set()
        commit_count = 0
        
        try:
            commits = self.provider.get_repository_commits(
                repo_full_name,
                start_date,
                end_date
            )
            
            for commit in commits:
                # Skip if no author information
                if not commit.author_username:
                    logger.debug(f"Skipping commit {commit.sha} - no author information")
                    continue
                
                # Check contributor filtering rules
                if not self.filter_manager.should_include_contributor(
                    commit.author_username,
                    commit.author_email
                ):
                    excluded_contributors.add(commit.author_username)
                    logger.debug(
                        f"\nSkipping excluded contributor: {commit.author_username}"
                    )
                    continue
                
                commit_count += 1
                self._update_contributor_stats(
                    commit,
                    contributors,
                    repo_contributors
                )
            
            # Update repository statistics
            repo_name = repo_full_name.split('/')[-1]  # Extract repo name from full name
            repositories[repo_name] = RepoStats(
                name=repo_name,
                contributor_count=len(repo_contributors),
                commit_count=commit_count,
                contributors=list(repo_contributors)
            )
            
            logger.debug(
                f"Processed {commit_count} commits from "
                f"{len(repo_contributors)} contributors in {repo_name}"
            )
            
        except Exception as e:
            logger.error(f"Error processing repository {repo_full_name}: {str(e)}")
            # Continue processing other repositories
            pass

    def _update_contributor_stats(
        self,
        commit,
        contributors: Dict[str, ContributorStats],
        repo_contributors: set
    ) -> None:
        """
        Update contributor statistics with commit information.
        
        Args:
            commit: Commit object containing author and timestamp information
            contributors: Dictionary of contributor statistics to update
            repo_contributors: Set of contributors for the current repository
        """
        username = commit.author_username
        repo_name = commit.repository.split('/')[-1]
        
        if username not in contributors:
            # New contributor
            contributors[username] = ContributorStats(
                username=username,
                email=commit.author_email,
                commit_count=1,
                first_commit=commit.date,
                last_commit=commit.date,
                repositories=[repo_name]
            )
        else:
            # Update existing contributor
            stats = contributors[username]
            stats.commit_count += 1
            stats.first_commit = min(stats.first_commit, commit.date)
            stats.last_commit = max(stats.last_commit, commit.date)
            if repo_name not in stats.repositories:
                stats.repositories.append(repo_name)
        
        repo_contributors.add(username)

