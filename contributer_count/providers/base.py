from abc import ABC, abstractmethod
from datetime import datetime
from typing import Iterator, Optional
from ..models import Commit, Repository

class GitProvider(ABC):
    """Abstract base class for Git providers."""
    
    @abstractmethod
    def __init__(self, token: str, url: Optional[str] = None):
        """Initialize provider with authentication token and optional base URL."""
        pass
    
    @abstractmethod
    def get_organization_repos(self, org_name: str) -> Iterator[Repository]:
        """Get all repositories for an organization."""
        pass
    
    @abstractmethod
    def get_repository_commits(
        self, 
        repo_full_name: str, 
        since: datetime,
        until: Optional[datetime] = None
    ) -> Iterator[Commit]:
        """Get all commits for a repository within date range."""
        pass
    
    @abstractmethod
    def close(self):
        """Clean up any resources."""
        pass