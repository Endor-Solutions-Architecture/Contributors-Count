# TODO: This counts all contributors. Need to add 90 day filter

import os
from github import Github
from github import Auth

auth = Auth.Token(os.getenv("GITHUB_TOKEN"))

gh = Github(auth=auth)

# Replace with the name of the GitHub organization you want to analyze
org_name = "Endor-Solutions-Architecture"

# Get the organization object
organization = gh.get_organization(org_name)

# Create a set to store unique contributors
contributors = set()

# Iterate through all the repositories in the organization
for repo in organization.get_repos():
    # Iterate through all the contributors of the repository
    for contributor in repo.get_contributors():
        contributors.add(contributor.login)

# Print the number of contributing developers
print(f"Number of contributing developers in {org_name}: {len(contributors)}")

gh.close()