import os
import datetime
from github import Github, GithubException
from github import Auth

# Create a Fine-Grained Token in GitHub with read-only permissions to Contents, Metadata, Email Addresses 
auth = Auth.Token(os.getenv("GITHUB_TOKEN"))
gh = Github(auth=auth)

# Replace with the name of the GitHub organization you want to analyze
org_name = "Endor-Solutions-Architecture"

# Get the organization object
organization = gh.get_organization(org_name)

# Create a dictionary to store unique contributors and their last commit info
contributors = {}

# Calculate the date 90 days ago
ninety_days_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=90)

# Fetch recent events for the organization
for event in organization.get_events():
    if event.created_at < ninety_days_ago:
        break
    
    if event.type == "PushEvent":
        for commit in event.payload['commits']:
            username = event.actor.login
            commit_date = event.created_at
            if username not in contributors or commit_date > contributors[username]['date']:
                contributors[username] = {
                    'date': commit_date,
                    'sha': commit['sha'],
                    'repo': event.repo.name
                }

# Print the number of contributing developers in the last 90 days
print(f"\nNumber of contributing developers in {org_name} in the last 90 days: {len(contributors)}")

# Print the usernames of all contributors with a commit date and URL
print("\nContributing developers with commit info from the last 90 days:\n")
for username, commit_info in sorted(contributors.items(), key=lambda x: x[1]['date'], reverse=True):
    commit_url = f"https://github.com/{commit_info['repo']}/commit/{commit_info['sha']}"
    print(f"- A commit date from {username} in the last 90 days: {commit_info['date'].strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"  Commit URL: {commit_url}\n")

gh.close()
