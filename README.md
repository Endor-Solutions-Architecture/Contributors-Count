# Contributing Developers Count

## Github

- Counts the number of contributing developers within the last 90 days of a given GitHub Organization
- Prints the name of each GitHub user, along with a link to a commit they've given in the last 90 days
- A GitHub PAT is required for authentication. The permissions needed are shown below, and we recommend to use fine-grained tokens:
<img width="895" alt="image" src="https://github.com/user-attachments/assets/7803c2f0-1631-45c3-9f61-8984ab11cc8f">

### Running the script:

- Create a venv with `python3 -m venv .venv` in the directory titled `GitHub`, and activate with `source .venv/bin/activate`
- Install dependencies with `pip3 install -r requirements.txt`
- Edit the org name for the variable called `org-name` to the GitHub organization of your choosing
- Run with the command `python3 github_contributor_count.py`

## Gitlab

- Counts the number of contributing developers within the last 90 days of a given Gitlab Organization
- Prints the groups and projects that are being analyzed
- Prints the contributor count for individual groups and orphan projects(Projects without groups) too.
- Prints the consolidated deduplicated report with name of each Gitlab user, along with a link to a commit they've given in the last 90 days

### Running the script:

- Create a venv with `python3 -m venv .venv` in the directory titled `Gitlab`, and activate with `source .venv/bin/activate`
- Install dependencies with `pip3 install -r requirements.txt`
- Edit the org name for the variable called `GITLAB_URL` to the Gitlab host incase you are using self hosted Gitlab instance
- Run with the command `python3 gitlab_contributor_count.py`

Note: The token used as GITLAB_TOKEN should have read_api and read_user access


_Support for other SCM providers coming soon!_

## No Warranty

Please be advised that this software is provided on an "as is" basis, without warranty of any kind, express or implied. The authors and contributors make no representations or warranties of any kind concerning the safety, suitability, lack of viruses, inaccuracies, typographical errors, or other harmful components of this software. There are inherent dangers in the use of any software, and you are solely responsible for determining whether this software is compatible with your equipment and other software installed on your equipment.

By using this software, you acknowledge that you have read this disclaimer, understand it, and agree to be bound by its terms and conditions. You also agree that the authors and contributors of this software are not liable for any damages you may suffer as a result of using, modifying, or distributing this software.