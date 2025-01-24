from datetime import datetime
from typing import Iterator, Optional
from github import Github, Auth
from .base import GitProvider
from ..models import Commit, Repository

class GitHubProvider(GitProvider):
    def __init__(self, token: str, url: Optional[str] = None):
        """
        Initialize GitHub provider.
        
        Args:
            token: GitHub authentication token
            url: Optional GitHub Enterprise URL
        """
        auth = Auth.Token(token)
        self.client = Github(auth=auth, base_url=url or "https://api.github.com")
    
    def get_organization_repos(self, org_name: str) -> Iterator[Repository]:
        org = self.client.get_organization(org_name)

        for repo in org.get_repos():
            yield Repository(
                name=repo.name,
                full_name=repo.full_name,
                private=repo.private,
                fork=repo.fork
            )
    
    def get_repository_commits(
        self,
        repo_full_name: str,
        since: datetime,
        until: Optional[datetime] = None
    ) -> Iterator[Commit]:
        repo = self.client.get_repo(repo_full_name)
        for commit in repo.get_commits(since=since, until=until):
            if commit.author:  # Only include commits with associated users
                yield Commit(
                    sha=commit.sha,
                    author_name=commit.commit.author.name,
                    author_email=commit.commit.author.email,
                    author_username=commit.author.login,
                    date=commit.commit.author.date,
                    repository=repo_full_name
                )
    
    def close(self):
        self.client.close()