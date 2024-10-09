# Contributing Developers Count

- Counts the number of contributing developers within the last 90 days of a given GitHub Organization
- Prints the name of each GitHub user, along with a link to a commit they've given in the last 90 days
- A GitHub PAT is required for authentication. The permissions needed are shown below, and we recommend to use fine-grained tokens:
<img width="895" alt="image" src="https://github.com/user-attachments/assets/7803c2f0-1631-45c3-9f61-8984ab11cc8f">

## Running the script:

- Create a venv with `python3 -m venv .venv` in the directory titled `GitHub`, and activate with `source .venv/bin/activate`
- Install dependencies with `pip3 install -r requirements.txt`
- Edit the org name for the variable called `org-name` to the GitHub organization of your choosing
- Run with the command `python3 github_contributor_count.py`

_Support for other SCM providers coming soon!_
