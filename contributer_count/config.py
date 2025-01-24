from dataclasses import dataclass
from typing import List, Optional
import yaml

@dataclass
class ProviderConfig:
    type: str
    org: str
    url: Optional[str] = None

    def __str__(self):
        return f"ProviderConfig(type={self.type}, org={self.org}, url={self.url})"

@dataclass
class RepoPattern:
    pattern: Optional[str] = None
    exact: Optional[str] = None

    def __str__(self):
        return f"RepoPattern(pattern={self.pattern}, exact={self.exact})"

@dataclass
class RepoConfig:
    include: List[RepoPattern]
    exclude: List[RepoPattern]

    def __str__(self):
        include_str = ', '.join(str(p) for p in self.include)
        exclude_str = ', '.join(str(p) for p in self.exclude)
        return f"RepoConfig(include=[{include_str}], exclude=[{exclude_str}])"

@dataclass
class ContributorExcludeRule:
    pattern: Optional[str] = None
    users: Optional[List[str]] = None
    emails: Optional[List[str]] = None
    domains: Optional[List[str]] = None

    def __str__(self):
        return (f"ContributorExcludeRule(pattern={self.pattern}, users={self.users}, "
                f"emails={self.emails}, domains={self.domains})")

@dataclass
class ContributorConfig:
    exclude: List[ContributorExcludeRule]

    def __str__(self):
        exclude_str = ', '.join(str(rule) for rule in self.exclude)
        return f"ContributorConfig(exclude=[{exclude_str}])"

@dataclass
class Config:
    provider: ProviderConfig
    repositories: RepoConfig
    contributors: ContributorConfig

    def __str__(self):
        return (f"Config(\n  provider={self.provider},\n"
                f"  repositories={self.repositories},\n"
                f"  contributors={self.contributors}\n)")

class ConfigLoader:
    @staticmethod
    def load(config_path: str) -> Config:
        """Load and validate configuration from YAML file."""
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)
            
        return ConfigLoader._parse_config(data)
    
    @staticmethod
    def _parse_config(data: dict) -> Config:
        """Parse and validate configuration dictionary."""
        provider_data = data.get('provider', {})

        provider = ProviderConfig(
            type=provider_data.get('type'),
            org=provider_data.get('org'),
            url=provider_data.get('url')
        )
        
        repo_data = data.get('repositories', {})
        repositories = RepoConfig(
            include=[
                RepoPattern(**pattern) 
                for pattern in repo_data.get('include', [])
            ],
            exclude=[
                RepoPattern(**pattern) 
                for pattern in repo_data.get('exclude', [])
            ]
        )
        
        contributor_data = data.get('contributors', {})
        contributors = ContributorConfig(
            exclude=[
                ContributorExcludeRule(**rule) 
                for rule in contributor_data.get('exclude', [])
            ]
        )
        
        return Config(provider, repositories, contributors)
