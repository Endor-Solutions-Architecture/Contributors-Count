import fnmatch
from typing import Optional
from .config import Config


class FilterManager:
    def __init__(self, config: Config):
        self.config = config
    
    def should_include_repo(self, repo_name: str) -> bool:
        """Check if a repository should be included based on configuration rules."""
        # Check explicit inclusions if any are specified
        if self.config.repositories.include:
            included = False
            for pattern in self.config.repositories.include:
                if pattern.exact and pattern.exact == repo_name:
                    included = True
                    break
                if pattern.pattern and fnmatch.fnmatch(repo_name, pattern.pattern):
                    included = True
                    break
            if not included:
                return False
        
        # Check exclusions
        for pattern in self.config.repositories.exclude:
            if pattern.exact and pattern.exact == repo_name:
                return False
            if pattern.pattern and fnmatch.fnmatch(repo_name, pattern.pattern):
                return False
        
        return True
    
    def should_include_contributor(self, username: str, email: Optional[str] = None) -> bool:
        """Check if a contributor should be included based on configuration rules."""
        for rule in self.config.contributors.exclude:
            # Check username pattern
            if rule.pattern and fnmatch.fnmatch(username, rule.pattern):
                return False
            
            # Check specific usernames
            if rule.users and username in rule.users:
                return False
            
            # Check email patterns
            if email and rule.emails:
                for email_pattern in rule.emails:
                    if fnmatch.fnmatch(email, email_pattern):
                        return False
            
            # Check domain patterns
            if email and rule.domains:
                domain = email.split('@')[-1]
                for domain_pattern in rule.domains:
                    if fnmatch.fnmatch(domain, domain_pattern):
                        return False
        
        return True