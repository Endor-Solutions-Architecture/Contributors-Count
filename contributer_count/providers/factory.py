from typing import Optional
from .base import GitProvider
from .github import GitHubProvider
from .gitlab import GitLabProvider

class ProviderFactory:
    @staticmethod
    def create_provider(
        provider_type: str,
        token: str,
        url: Optional[str] = None
    ) -> GitProvider:
        """Create a Git provider instance based on type."""
        providers = {
            'github': GitHubProvider,
            'gitlab': GitLabProvider,
        }
        
        if provider_type not in providers:
            raise ValueError(f"Unsupported provider type: {provider_type}")
        
        return providers[provider_type](token, url)