import gitlab
import os
import datetime

# Configure your GitLab API token and GitLab instance URL
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")  # Set this as an environment variable
GITLAB_URL = "https://gitlab.com"  # Replace with your GitLab instance URL, if self-hosted

# Initialize the GitLab connection
gl = gitlab.Gitlab(GITLAB_URL, private_token=GITLAB_TOKEN)

# Create a dictionary to store unique contributors for all groups and standalone projects
all_contributors = {}
unique_contributors = {}

# Calculate the date 90 days ago
ninety_days_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=90)

# Fetch all groups the user has access to
for group in gl.groups.list(all=True):  # Fetch all groups (pagination handled internally)
    group_name = group.name
    print(f"\nAnalyzing group: {group_name}")

    # Create a dictionary to store unique contributors for this group
    contributors = {}

    # Fetch all projects in the group
    for project in group.projects.list(all=True):
        project = gl.projects.get(project.id)
        print(f"  Analyzing project: {project.name}")

        # Fetch recent commits for the project
        commits = project.commits.list(since=ninety_days_ago.isoformat(), all=True)
        for commit in commits:
            username = commit.author_name
            try:
                commit_date = datetime.datetime.fromisoformat(commit.created_at.rstrip('Z'))
            except ValueError:
                commit_date = datetime.datetime.strptime(commit.created_at, "%Y-%m-%dT%H:%M:%S.%f%z")
            if username not in contributors or commit_date > contributors[username]['date']:
                contributors[username] = {
                    'date': commit_date,
                    'sha': commit.id,
                    'repo': project.name
                }

                # Add to unique contributors
                if username not in unique_contributors or commit_date > unique_contributors[username]['date']:
                    unique_contributors[username] = {
                        'date': commit_date,
                        'sha': commit.id,
                        'repo': project.name
                    }

    # Add group contributors to the global list
    all_contributors[group_name] = contributors

# Fetch all projects the user has access to (including membership)
print("\nAnalyzing all accessible projects:")
accessible_contributors = {}
for project in gl.projects.list(membership=True, all=True):  # Fetch all projects the user is a member of
    print(f"  Analyzing project: {project.name}")

    # Fetch recent commits for the project
    commits = project.commits.list(since=ninety_days_ago.isoformat(), all=True)
    for commit in commits:
        username = commit.author_name
        try:
            commit_date = datetime.datetime.fromisoformat(commit.created_at.rstrip('Z'))
        except ValueError:
            commit_date = datetime.datetime.strptime(commit.created_at, "%Y-%m-%dT%H:%M:%S.%f%z")
        if username not in accessible_contributors or commit_date > accessible_contributors[username]['date']:
            accessible_contributors[username] = {
                'date': commit_date,
                'sha': commit.id,
                'repo': project.name
            }

            # Add to unique contributors
            if username not in unique_contributors or commit_date > unique_contributors[username]['date']:
                unique_contributors[username] = {
                    'date': commit_date,
                    'sha': commit.id,
                    'repo': project.name
                }

# Add standalone project contributors to the global list
all_contributors["Standalone Projects"] = accessible_contributors

# Print the results
for group_name, contributors in all_contributors.items():
    print(f"\nNumber of contributing developers in {group_name} in the last 90 days: {len(contributors)}")

    print("\nContributing developers with commit info from the last 90 days:\n")
    for username, commit_info in sorted(contributors.items(), key=lambda x: x[1]['date'], reverse=True):
        commit_url = f"{GITLAB_URL}/{commit_info['repo']}/-/commit/{commit_info['sha']}"
        print(f"- {username}: {commit_info['date'].strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"  Commit URL: {commit_url}\n")

# Print consolidated view of all unique contributors
print("\nConsolidated view of all unique contributors in the last 90 days:")
print(f"\nTotal unique contributors: {len(unique_contributors)}")
for username, commit_info in sorted(unique_contributors.items(), key=lambda x: x[1]['date'], reverse=True):
    commit_url = f"{GITLAB_URL}/{commit_info['repo']}/-/commit/{commit_info['sha']}"
    print(f"- {username}: {commit_info['date'].strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"  Commit URL: {commit_url}\n")
