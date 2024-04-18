import os
import datetime
from github import Github
from github import Auth

auth = Auth.Token(os.getenv("GITHUB_TOKEN"))
gh = Github(auth=auth)

# Replace with the name of the GitHub organization you want to analyze
org_name = "Your GitHub Org"

# Get the organization object
organization = gh.get_organization(org_name)

# Create a set to store unique contributors
contributors = set()

# Calculate the date 90 days ago
ninety_days_ago = datetime.datetime.now() - datetime.timedelta(days=90)

# Iterate through all the repositories in the organization
for repo in organization.get_repos():
    # Iterate through all the contributors of the repository who have contributed in the last 90 days
    for contributor in repo.get_contributors(since=ninety_days_ago):
        contributors.add(contributor.login)

# Print the number of contributing developers in the last 90 days
print(f"Number of contributing developers in {org_name} in the last 90 days: {len(contributors)}")

gh.close()
