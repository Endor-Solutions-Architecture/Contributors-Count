from datetime import datetime
from typing import Iterator, Optional
import gitlab
from .base import GitProvider
from ..models import Commit, Repository

class GitLabProvider(GitProvider):
    def __init__(self, token: str, url: Optional[str] = None):
        """
        Initialize GitLab provider.
        
        Args:
            token: Gitlab personal access token
            url: Optional self-hosted Gitlab URL
        """
        self.client = gitlab.Gitlab(url or 'https://gitlab.com', private_token=token)
        self.client.auth()
    
    def get_organization_repos(self, org_name: str) -> Iterator[Repository]:
        group = self.client.groups.get(org_name)
        for project in group.projects.list(all=True):
            project_obj = self.client.projects.get(project.id)
            yield Repository(
                name=project_obj.name,
                full_name=project_obj.path_with_namespace,
                private=project_obj.visibility == 'private',
                fork=project_obj.forks is not None
            )
    
    def get_repository_commits(
        self,
        repo_full_name: str,
        since: datetime,
        until: Optional[datetime] = None
    ) -> Iterator[Commit]:
        project = self.client.projects.get(repo_full_name)
        commits = project.commits.list(
            since=since.isoformat(),
            until=until.isoformat() if until else None,
            all=True
        )
        
        for commit in commits:
            commit_detail = project.commits.get(commit.id)
            yield Commit(
                sha=commit_detail.id,
                author_name=commit_detail.author_name,
                author_email=commit_detail.author_email,
                author_username=commit_detail.author_name,  # GitLab may not provide usernames like GitHub
                date=datetime.fromisoformat(commit_detail.created_at),
                repository=repo_full_name
            )
    
    def close(self):
        self.client.session.close()