import os
import time
import datetime
from github import Github, GithubException, RateLimitExceededException
from github import Auth

# GitHub Token Authentication
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
auth = Auth.Token(GITHUB_TOKEN)
gh = Github(auth=auth)

# Organization to analyze
ORG_NAME = "endorlabs"

# Calculate the date 90 days ago
ninety_days_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=90)

# Dictionary to store unique contributors and their last commit info
contributors = {}

# Function to handle rate limits using exponential backoff
def handle_rate_limit_exponential():
    """Waits using exponential backoff when the GitHub rate limit is exceeded."""
    rate_limit = gh.get_rate_limit().core
    if rate_limit.remaining == 0:
        reset_time = rate_limit.reset.timestamp()
        sleep_time = reset_time - time.time()
        if sleep_time > 0:
            print(f"Rate limit exceeded. Sleeping for {round(sleep_time / 60, 2)} minutes...")
            time.sleep(sleep_time + 1)  # Wait until reset

# Exponential Backoff Function
def exponential_backoff(attempt):
    """Waits exponentially longer on repeated failures (max 10 minutes)."""
    wait_time = min(2 ** attempt, 600)  # Max wait time: 600 seconds (10 minutes)
    print(f"Backing off for {wait_time} seconds before retrying...")
    time.sleep(wait_time)

# Fetch all repositories (including private)
try:
    repos = gh.get_organization(ORG_NAME).get_repos()
except GithubException as e:
    print(f"Error fetching repositories: {e}")
    exit(1)

for repo in repos:
    print(f"Processing repository: {repo.full_name}")

    page = 0
    attempt = 0  # Track failed attempts for backoff
    while True:
        try:
            handle_rate_limit_exponential()  # Check if we need to wait for the rate limit reset
            commits = repo.get_commits(since=ninety_days_ago).get_page(page)
            if not commits:
                break  # No more commits, exit loop

            for commit in commits:
                if commit.author is not None:
                    username = commit.author.login
                    commit_date = commit.commit.author.date
                    if commit_date >= ninety_days_ago:
                        if username not in contributors or commit_date > contributors[username]['date']:
                            contributors[username] = {
                                'date': commit_date,
                                'sha': commit.sha,
                                'repo': repo.full_name
                            }

            page += 1
            attempt = 0  # Reset attempt counter on success

        except RateLimitExceededException:
            handle_rate_limit_exponential()  # Handle GitHub rate limit and retry
        except GithubException as e:
            attempt += 1
            if attempt > 5:  # Stop after 5 failed attempts
                print(f"Max retries reached for {repo.full_name}. Skipping...")
                break
            exponential_backoff(attempt)  # Apply backoff before retrying

# Print contributors
print(f"\nNumber of contributing developers in {ORG_NAME} in the last 90 days: {len(contributors)}")
for username, commit_info in sorted(contributors.items(), key=lambda x: x[1]['date'], reverse=True):
    commit_url = f"https://github.com/{commit_info['repo']}/commit/{commit_info['sha']}"
    print(f"- {username} committed on {commit_info['date'].strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"  Commit URL: {commit_url}\n")

gh.close()
