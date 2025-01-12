import os
import datetime
from github import Github, GithubException
from github import Auth

# Create a Fine-Grained Token in GitHub with read-only permissions to Contents, Metadata, Email Addresses 
auth = Auth.Token(os.getenv("GITHUB_TOKEN"))
gh = Github(auth=auth)

# Replace with the name of the GitHub organization you want to analyze
org_name = "endorlabs"

# Get the organization object
organization = gh.get_organization(org_name)

# Create a dictionary to store unique contributors and their last commit info
contributors = {}

# Calculate the date 90 days ago
ninety_days_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=90)

# Fetch all repositories (including private)
for repo in organization.get_repos():
    print(f"Processing repository: {repo.full_name}")

    # Get commits for the repository
    try:
        # The GitHub API's since parameter only filters commits by their author date (the date the commit was authored) and not the pushed date. 
        # If a commit was authored before 90 days but pushed recently, it will still be included in the results.
        commits = repo.get_commits(since=ninety_days_ago)
        for commit in commits:
            if commit.author is not None:  # Only consider commits with an associated GitHub user
                username = commit.author.login
                commit_date = commit.commit.author.date
                # Additional filter to include only commits authored 90 days ago
                if commit_date >= ninety_days_ago: 
                    # Store the most recent commit for each contributor
                    if username not in contributors or commit_date > contributors[username]['date']:
                        contributors[username] = {
                            'date': commit_date,
                            'sha': commit.sha,
                            'repo': repo.full_name
                        }
    except GithubException as e:
        print(f"Error processing commits for repository {repo.full_name}: {e}")

# Print the number of contributing developers in the last 90 days
print(f"\nNumber of contributing developers in {org_name} in the last 90 days: {len(contributors)}")

# Print the usernames of all contributors with a commit date and URL
print("\nContributing developers with commit info from the last 90 days:\n")
for username, commit_info in sorted(contributors.items(), key=lambda x: x[1]['date'], reverse=True):
    commit_url = f"https://github.com/{commit_info['repo']}/commit/{commit_info['sha']}"
    print(f"- A commit date from {username} in the last 90 days: {commit_info['date'].strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"  Commit URL: {commit_url}\n")

gh.close()
