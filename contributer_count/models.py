from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

@dataclass
class Commit:
    sha: str
    author_name: str
    author_email: Optional[str]
    author_username: str
    date: datetime
    repository: str

@dataclass
class Repository:
    name: str
    full_name: str
    private: bool
    fork: bool

@dataclass
class ContributorStats:
    username: str
    email: Optional[str]
    commit_count: int
    first_commit: datetime
    last_commit: datetime
    repositories: List[str]

@dataclass
class RepoStats:
    name: str
    contributor_count: int
    commit_count: int
    contributors: List[str]
