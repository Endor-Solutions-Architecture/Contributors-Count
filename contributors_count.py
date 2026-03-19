#!/usr/bin/env python3
"""
Unified Cross-Platform Contributors Count

Scans multiple SCM platforms in a single run and produces a consolidated,
cross-platform deduplicated contributor count.

Usage:
  python contributors_count.py --config platforms.json
  python contributors_count.py --config platforms.json --days 30 --exclude-bots
  python contributors_count.py --config platforms.json --format markdown > report.md

Configuration:
  Create a platforms.json specifying which platforms to scan.
  See platforms.json.example for the template.
  Tokens should be set via environment variables (not in the config file).
"""

import os
import sys
import json
import time
import datetime
from dataclasses import dataclass, field
from typing import Dict, Set, List, Tuple, Any, Optional, Callable, Generator
from concurrent.futures import ThreadPoolExecutor, as_completed

import click

# Add platform directories to Python path
_ROOT = os.path.dirname(os.path.abspath(__file__))
for _dir in ("GitHub", "Gitlab", "bitbucket", "azure_devops"):
    _path = os.path.join(_ROOT, _dir)
    if _path not in sys.path:
        sys.path.insert(0, _path)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PlatformResult:
    """Normalized result from scanning a single platform."""
    platform: str
    label: str
    contributors: Dict[str, Set[str]]
    repos_scanned: int
    total_commits: int
    skipped_repos: List[str]
    elapsed: float


# ---------------------------------------------------------------------------
# Union-Find for cross-platform deduplication
# ---------------------------------------------------------------------------

class _UnionFind:
    """Disjoint-set with path compression and union by rank."""

    def __init__(self) -> None:
        self._parent: Dict[Any, Any] = {}
        self._rank: Dict[Any, int] = {}

    def find(self, x: Any) -> Any:
        if x not in self._parent:
            self._parent[x] = x
            self._rank[x] = 0
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, a: Any, b: Any) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self._rank[ra] < self._rank[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        if self._rank[ra] == self._rank[rb]:
            self._rank[ra] += 1

    def groups(self) -> Dict[Any, List[Any]]:
        result: Dict[Any, List[Any]] = {}
        for x in self._parent:
            root = self.find(x)
            if root not in result:
                result[root] = []
            result[root].append(x)
        return result


def _cross_dedup(
    results: List[PlatformResult],
) -> Tuple[int, List[Dict[str, Any]]]:
    """Merge contributors across platforms by shared email.

    Returns (unique_count, merged_list) where each entry has
    display name, platform memberships, and merged email set.
    """
    uf = _UnionFind()
    email_to_key: Dict[str, Tuple[str, str]] = {}
    key_emails: Dict[Tuple[str, str], Set[str]] = {}

    for result in results:
        for identifier, emails in result.contributors.items():
            key = (result.platform, identifier)
            uf.find(key)
            key_emails[key] = emails

            for email in emails:
                if email in email_to_key:
                    uf.union(key, email_to_key[email])
                else:
                    email_to_key[email] = key

    groups = uf.groups()

    merged: List[Dict[str, Any]] = []
    for _root, members in groups.items():
        all_emails: Set[str] = set()
        member_info: List[Dict[str, str]] = []
        for key in members:
            platform, ident = key
            member_info.append({"platform": platform, "identifier": ident})
            all_emails.update(key_emails.get(key, set()))
        merged.append({
            "members": member_info,
            "emails": sorted(all_emails),
            "display": member_info[0]["identifier"],
        })

    merged.sort(key=lambda x: x["display"].lower())
    return len(merged), merged


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _elapsed(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s" if m else f"{s}s"


def _load_config(config_path: str) -> Dict[str, Any]:
    with open(config_path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Platform scanners
# ---------------------------------------------------------------------------

def _scan_github(
    config: Dict[str, Any], days: int, exclude_bots: bool,
    vlog: Callable[[str], None],
) -> PlatformResult:
    from github_contributors_90d import (
        GitHubClient, fetch_repos, _scan_repo, ApiError,
    )

    org = config["org"]
    token = config.get("token") or os.environ.get("GITHUB_TOKEN")
    base_url = config.get("base_url", "https://api.github.com")
    default_branch_only = config.get("default_branch_only", False)
    max_repos = config.get("max_repos")

    vlog(f"GitHub: org={org}, base_url={base_url}")

    client = GitHubClient(token, base_url)
    now = datetime.datetime.now(datetime.timezone.utc)
    start_date = now - datetime.timedelta(days=days)
    since_iso = start_date.isoformat()
    until_iso = now.isoformat()

    t0 = time.monotonic()
    try:
        repos = fetch_repos(client, org, max_repos)
    except ApiError as exc:
        raise RuntimeError(f"GitHub: {exc}")

    vlog(f"GitHub: {len(repos)} repositories found")

    global_contribs: Dict[str, Set[str]] = {}
    total_commits = 0
    skipped_repos: List[str] = []
    repo_commit_counts: List[Tuple[str, int]] = []
    workers = min(4, len(repos)) if repos else 1

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _scan_repo, client, repo,
                since_iso, until_iso,
                default_branch_only, exclude_bots,
            ): repo
            for repo in repos
        }
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception:
                skipped_repos.append(
                    futures[future].get("full_name", "unknown"),
                )
                continue

            repo_commit_counts.append(
                (result["repo_name"], result["commit_count"]),
            )
            for login, emails in result["contributors"].items():
                if login not in global_contribs:
                    global_contribs[login] = set()
                global_contribs[login].update(emails)
            total_commits += result["commit_count"]

    elapsed = time.monotonic() - t0
    vlog(
        f"GitHub: {len(global_contribs)} contributors, "
        f"{total_commits:,} commits in {_elapsed(elapsed)}",
    )

    return PlatformResult(
        platform="GitHub",
        label=f"GitHub: {org}",
        contributors=global_contribs,
        repos_scanned=len(repo_commit_counts),
        total_commits=total_commits,
        skipped_repos=skipped_repos,
        elapsed=elapsed,
    )


def _scan_gitlab(
    config: Dict[str, Any], days: int, exclude_bots: bool,
    vlog: Callable[[str], None],
) -> PlatformResult:
    try:
        import gitlab as gitlab_lib
    except ImportError:
        raise RuntimeError(
            "GitLab: python-gitlab is required. "
            "Install with: pip install python-gitlab",
        )

    from gitlab_contributor_count import _process_project

    url = config.get("url", "https://gitlab.com")
    token = config.get("token") or os.environ.get("GITLAB_TOKEN")
    if not token:
        raise RuntimeError("GitLab: GITLAB_TOKEN is required")

    vlog(f"GitLab: url={url}")

    gl = gitlab_lib.Gitlab(
        url, private_token=token, timeout=30,
        retry_transient_errors=True,
        user_agent="contributors-count/1.0",
    )

    now = datetime.datetime.now(datetime.timezone.utc)
    start_date = now - datetime.timedelta(days=days)
    since_iso = start_date.isoformat()

    t0 = time.monotonic()
    unique_contributors: Dict[str, dict] = {}
    scanned_project_ids: Set[int] = set()
    skipped_projects: List[str] = []
    total_commits = 0

    try:
        groups = gl.groups.list(all=True)
    except Exception as exc:
        raise RuntimeError(f"GitLab: error listing groups: {exc}")

    vlog(f"GitLab: {len(groups)} groups found")

    for group in groups:
        contributors: Dict[str, dict] = {}
        try:
            group_projects = group.projects.list(all=True)
        except Exception:
            continue
        for gp in group_projects:
            scanned_project_ids.add(gp.id)
            cc, _ = _process_project(
                gl, gp.id, since_iso,
                contributors, unique_contributors, url,
                exclude_bots=exclude_bots,
                skipped_projects=skipped_projects,
            )
            total_commits += cc

    try:
        membership_projects = gl.projects.list(membership=True, all=True)
    except Exception:
        membership_projects = []

    standalone: Dict[str, dict] = {}
    for project in membership_projects:
        if project.id in scanned_project_ids:
            continue
        scanned_project_ids.add(project.id)
        cc, _ = _process_project(
            gl, project.id, since_iso,
            standalone, unique_contributors, url,
            exclude_bots=exclude_bots,
            skipped_projects=skipped_projects,
        )
        total_commits += cc

    normalized: Dict[str, Set[str]] = {}
    for ident, info in unique_contributors.items():
        normalized[ident] = set()
        email = info.get("email")
        if email:
            normalized[ident].add(email)

    elapsed = time.monotonic() - t0
    vlog(
        f"GitLab: {len(normalized)} contributors, "
        f"{total_commits:,} commits in {_elapsed(elapsed)}",
    )

    return PlatformResult(
        platform="GitLab",
        label=f"GitLab: {url}",
        contributors=normalized,
        repos_scanned=len(scanned_project_ids),
        total_commits=total_commits,
        skipped_repos=skipped_projects,
        elapsed=elapsed,
    )


def _scan_bitbucket_cloud(
    config: Dict[str, Any], days: int, exclude_bots: bool,
    vlog: Callable[[str], None],
) -> PlatformResult:
    from bitbucket_contributors_90d import (
        BitbucketClient, fetch_repos, _fetch_commits, _is_bot, ApiError,
    )

    workspace = config["workspace"]
    user = config.get("user") or os.environ.get("BITBUCKET_USER")
    password = config.get("password") or os.environ.get("BITBUCKET_PASSWORD")
    if not user or not password:
        raise RuntimeError(
            "Bitbucket Cloud: BITBUCKET_USER and BITBUCKET_PASSWORD required",
        )

    vlog(f"Bitbucket Cloud: workspace={workspace}")

    client = BitbucketClient(user, password)
    now = datetime.datetime.now(datetime.timezone.utc)
    start_date = now - datetime.timedelta(days=days)
    since_iso = start_date.isoformat()

    t0 = time.monotonic()
    try:
        repos = fetch_repos(client, workspace)
    except ApiError as exc:
        raise RuntimeError(f"Bitbucket Cloud: {exc}")

    vlog(f"Bitbucket Cloud: {len(repos)} repositories found")

    contributors_map: Dict[str, Set[str]] = {}
    total_commits = 0
    skipped_repos: List[str] = []

    for repo in repos:
        repo_name: str = repo["name"]
        repo_slug: str = repo["slug"]
        commit_count = 0
        try:
            for commit in _fetch_commits(
                client, workspace, repo_slug, since_iso,
            ):
                author = commit.get("author", {})
                raw: Optional[str] = author.get("raw")
                user_info: Dict[str, Any] = author.get("user", {})

                raw_name = (
                    raw.split("<")[0].strip()
                    if raw and "<" in raw else (raw or "")
                )
                email: Optional[str] = None
                if raw and "<" in raw and ">" in raw:
                    email = raw.split("<")[-1].strip(">")

                if exclude_bots and _is_bot(raw_name, email):
                    continue

                identifier: Optional[str] = None
                if "account_id" in user_info:
                    identifier = user_info["account_id"]
                elif raw:
                    identifier = email if ("<" in raw and ">" in raw) else raw

                if identifier:
                    if identifier not in contributors_map:
                        contributors_map[identifier] = set()
                    if email:
                        contributors_map[identifier].add(email)

                commit_count += 1
            total_commits += commit_count
        except Exception:
            skipped_repos.append(repo_name)

    elapsed = time.monotonic() - t0
    vlog(
        f"Bitbucket Cloud: {len(contributors_map)} contributors, "
        f"{total_commits:,} commits in {_elapsed(elapsed)}",
    )

    return PlatformResult(
        platform="Bitbucket Cloud",
        label=f"Bitbucket Cloud: {workspace}",
        contributors=contributors_map,
        repos_scanned=len(repos) - len(skipped_repos),
        total_commits=total_commits,
        skipped_repos=skipped_repos,
        elapsed=elapsed,
    )


def _scan_bitbucket_server(
    config: Dict[str, Any], days: int, exclude_bots: bool,
    vlog: Callable[[str], None],
) -> PlatformResult:
    from bitbucket_server_contributors_90d import (
        BitbucketServerClient, fetch_repos, _fetch_commits,
        _is_bot, ApiError,
    )

    project = config["project"]
    url = config["url"]
    user = config.get("user") or os.environ.get("BITBUCKET_USER")
    password = config.get("password") or os.environ.get("BITBUCKET_PASSWORD")
    if not user or not password:
        raise RuntimeError(
            "Bitbucket Server: BITBUCKET_USER and BITBUCKET_PASSWORD required",
        )

    vlog(f"Bitbucket Server: project={project}, url={url}")

    client = BitbucketServerClient(url, user, password)
    now = datetime.datetime.now(datetime.timezone.utc)
    start_date = now - datetime.timedelta(days=days)
    since_timestamp_ms = int(start_date.timestamp() * 1000)

    t0 = time.monotonic()
    try:
        repos = fetch_repos(client, project)
    except ApiError as exc:
        raise RuntimeError(f"Bitbucket Server: {exc}")

    vlog(f"Bitbucket Server: {len(repos)} repositories found")

    contributors_map: Dict[str, Set[str]] = {}
    total_commits = 0
    skipped_repos: List[str] = []

    for repo in repos:
        repo_name: str = repo["name"]
        repo_slug: str = repo["slug"]
        commit_count = 0
        try:
            for commit in _fetch_commits(
                client, project, repo_slug, since_timestamp_ms,
            ):
                author = commit.get("author", {})
                email: Optional[str] = author.get("emailAddress")
                name: Optional[str] = author.get("name")

                if exclude_bots and _is_bot(name or "", email):
                    continue

                commit_count += 1
                identifier = email if email else name
                if identifier:
                    if identifier not in contributors_map:
                        contributors_map[identifier] = set()
                    if email:
                        contributors_map[identifier].add(email)
            total_commits += commit_count
        except Exception:
            skipped_repos.append(repo_name)

    elapsed = time.monotonic() - t0
    vlog(
        f"Bitbucket Server: {len(contributors_map)} contributors, "
        f"{total_commits:,} commits in {_elapsed(elapsed)}",
    )

    return PlatformResult(
        platform="Bitbucket Server",
        label=f"Bitbucket Server: {project} ({url})",
        contributors=contributors_map,
        repos_scanned=len(repos) - len(skipped_repos),
        total_commits=total_commits,
        skipped_repos=skipped_repos,
        elapsed=elapsed,
    )


def _scan_ado(
    config: Dict[str, Any], days: int, exclude_bots: bool,
    vlog: Callable[[str], None],
) -> PlatformResult:
    from ado_contributors_90d import (
        ADOClient, fetch_repos, _fetch_commits, _is_bot, ApiError,
    )

    org = config["org"]
    project = config["project"]
    token = config.get("token") or os.environ.get("ADO_TOKEN")
    if not token:
        raise RuntimeError("Azure DevOps: ADO_TOKEN is required")

    vlog(f"Azure DevOps: org={org}, project={project}")

    client = ADOClient(token, org)
    now = datetime.datetime.now(datetime.timezone.utc)
    start_date = now - datetime.timedelta(days=days)
    since_iso = start_date.isoformat()
    until_iso = now.isoformat()

    t0 = time.monotonic()
    try:
        repos = fetch_repos(client, project)
    except ApiError as exc:
        raise RuntimeError(f"Azure DevOps: {exc}")

    vlog(f"Azure DevOps: {len(repos)} repositories found")

    contributors_map: Dict[str, Set[str]] = {}
    total_commits = 0
    skipped_repos: List[str] = []

    for repo in repos:
        repo_name: str = repo["name"]
        repo_id: str = repo["id"]
        commit_count = 0
        try:
            for commit in _fetch_commits(
                client, project, repo_id, since_iso, until_iso,
            ):
                commit_count += 1
                author = commit.get("author", {})
                email: Optional[str] = author.get("email")
                name: Optional[str] = author.get("name")

                if exclude_bots and _is_bot(name or "", email):
                    continue

                identifier = email if email else name
                if identifier:
                    if identifier not in contributors_map:
                        contributors_map[identifier] = set()
                    if email:
                        contributors_map[identifier].add(email)
            total_commits += commit_count
        except Exception:
            skipped_repos.append(repo_name)

    elapsed = time.monotonic() - t0
    vlog(
        f"Azure DevOps: {len(contributors_map)} contributors, "
        f"{total_commits:,} commits in {_elapsed(elapsed)}",
    )

    return PlatformResult(
        platform="Azure DevOps",
        label=f"Azure DevOps: {project} ({org})",
        contributors=contributors_map,
        repos_scanned=len(repos) - len(skipped_repos),
        total_commits=total_commits,
        skipped_repos=skipped_repos,
        elapsed=elapsed,
    )


# ---------------------------------------------------------------------------
# Scanner registry
# ---------------------------------------------------------------------------

_SCANNERS: Dict[str, Callable] = {
    "github": _scan_github,
    "gitlab": _scan_gitlab,
    "bitbucket_cloud": _scan_bitbucket_cloud,
    "bitbucket_server": _scan_bitbucket_server,
    "azure_devops": _scan_ado,
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option(
    "--config", "-c", required=True,
    type=click.Path(exists=True),
    help="Path to platforms.json config file.",
)
@click.option(
    "--days", "-d", type=int, default=90, show_default=True,
    help="Number of days to look back for contributions.",
)
@click.option(
    "--exclude-bots", is_flag=True,
    help="Exclude bot/service accounts from the contributor count.",
)
@click.option(
    "--verbose", "-v", is_flag=True,
    help="Print API diagnostics to stderr.",
)
@click.option(
    "--format", "output_format",
    type=click.Choice(["text", "json", "markdown"]),
    default="text", help="Output format.",
)
@click.option(
    "--list-contributors", is_flag=True,
    help="List individual contributors and their emails.",
)
def main(config, days, exclude_bots, verbose, output_format, list_contributors):
    """
    Scan multiple SCM platforms and produce a consolidated, cross-platform
    deduplicated contributor count.
    """
    def vlog(msg: str) -> None:
        if verbose:
            click.echo(f"  [verbose] {msg}", err=True)

    if days < 1:
        click.echo("Error: --days must be at least 1.", err=True)
        sys.exit(1)

    cfg = _load_config(config)
    platforms_to_scan = [k for k in cfg if k in _SCANNERS]

    if not platforms_to_scan:
        click.echo(
            "Error: no valid platforms found in config. "
            f"Supported keys: {', '.join(_SCANNERS)}",
            err=True,
        )
        sys.exit(1)

    if output_format == "text":
        click.echo(
            f"Scanning {len(platforms_to_scan)} platform(s): "
            f"{', '.join(platforms_to_scan)}",
        )
        click.echo(
            f"Time window: {days} days | "
            f"Exclude bots: {'Yes' if exclude_bots else 'No'}\n",
        )

    t0 = time.monotonic()
    now = datetime.datetime.now(datetime.timezone.utc)
    results: List[PlatformResult] = []
    failed_platforms: List[Tuple[str, str]] = []

    for platform_key in platforms_to_scan:
        scanner = _SCANNERS[platform_key]
        platform_cfg = cfg[platform_key]

        if output_format == "text":
            click.echo(f"--- {platform_key} ---")

        try:
            result = scanner(platform_cfg, days, exclude_bots, vlog)
            results.append(result)
            if output_format == "text":
                click.echo(
                    f"  {result.repos_scanned} repos, "
                    f"{result.total_commits:,} commits, "
                    f"{len(result.contributors)} contributors "
                    f"({_elapsed(result.elapsed)})",
                )
                if result.skipped_repos:
                    click.echo(
                        f"  Skipped: {len(result.skipped_repos)} repo(s)",
                    )
                click.echo()
        except RuntimeError as exc:
            failed_platforms.append((platform_key, str(exc)))
            click.echo(
                f"  Error scanning {platform_key}: {exc}", err=True,
            )
            click.echo()

    if not results:
        click.echo("Error: all platform scans failed.", err=True)
        sys.exit(1)

    elapsed = time.monotonic() - t0

    per_platform_count = sum(len(r.contributors) for r in results)
    total_repos = sum(r.repos_scanned for r in results)
    total_commits = sum(r.total_commits for r in results)

    unique_count, merged = _cross_dedup(results)

    vlog(f"Per-platform sum: {per_platform_count} contributors")
    vlog(f"After cross-platform dedup: {unique_count} unique contributors")

    # -- Output --------------------------------------------------------------
    if output_format == "json":
        payload: Dict[str, Any] = {
            "scan_date": now.strftime("%Y-%m-%d"),
            "days": days,
            "exclude_bots": exclude_bots,
            "platforms_scanned": len(results),
            "platforms_failed": [p for p, _ in failed_platforms],
            "total_repositories": total_repos,
            "total_commits": total_commits,
            "per_platform_contributor_sum": per_platform_count,
            "unique_contributors_cross_platform": unique_count,
            "platforms": {},
        }
        for r in results:
            payload["platforms"][r.platform] = {
                "label": r.label,
                "contributors": len(r.contributors),
                "repos_scanned": r.repos_scanned,
                "commits": r.total_commits,
                "skipped_repos": r.skipped_repos,
            }
        if list_contributors:
            payload["contributors_details"] = [
                {
                    "display": m["display"],
                    "platforms": [
                        f"{mi['platform']}: {mi['identifier']}"
                        for mi in m["members"]
                    ],
                    "emails": m["emails"],
                }
                for m in merged
            ]
        click.echo(json.dumps(payload, indent=2))

    elif output_format == "markdown":
        lines = [
            "# Cross-Platform Contributors Report",
            "",
            "| Field | Value |",
            "|-------|-------|",
            f"| **Scan Date** | {now.strftime('%Y-%m-%d')} |",
            f"| **Time Window** | {days} days |",
            f"| **Platforms Scanned** | {len(results)} |",
            f"| **Total Repositories** | {total_repos} |",
            f"| **Bots Excluded** | {'Yes' if exclude_bots else 'No'} |",
            f"| **Scan Duration** | {_elapsed(elapsed)} |",
            "",
            f"## Unique Contributors "
            f"(cross-platform deduplicated): {unique_count}",
            "",
            "### Per-Platform Summary",
            "",
            "| Platform | Repos | Commits | Contributors |",
            "|----------|-------|---------|--------------|",
        ]
        for r in results:
            lines.append(
                f"| {r.label} | {r.repos_scanned} | "
                f"{r.total_commits:,} | {len(r.contributors)} |",
            )
        lines.append("")

        if per_platform_count != unique_count:
            lines.append(
                f"> **Cross-platform dedup:** {per_platform_count} "
                f"per-platform total → **{unique_count}** unique "
                f"(merged {per_platform_count - unique_count} "
                f"duplicate(s) by shared email)",
            )
            lines.append("")

        if list_contributors and merged:
            lines.append("### Contributors")
            lines.append("")
            lines.append(
                "| # | Contributor | Platform(s) | Email(s) |",
            )
            lines.append(
                "|---|-------------|-------------|----------|",
            )
            for i, m in enumerate(merged, 1):
                platforms_str = ", ".join(
                    mi["platform"] for mi in m["members"]
                )
                emails_str = ", ".join(m["emails"]) or "N/A"
                lines.append(
                    f"| {i} | {m['display']} | "
                    f"{platforms_str} | {emails_str} |",
                )
            lines.append("")

        all_skipped: List[str] = []
        for r in results:
            all_skipped.extend(
                f"{r.platform}: {s}" for s in r.skipped_repos
            )
        if all_skipped:
            lines.append(
                f"> **Note:** {len(all_skipped)} repo(s) skipped: "
                + ", ".join(all_skipped),
            )
            lines.append("")

        if failed_platforms:
            lines.append(
                f"> **Warning:** {len(failed_platforms)} platform(s) "
                f"failed: " + ", ".join(p for p, _ in failed_platforms),
            )
            lines.append("")

        lines.append("---")
        lines.append(
            "*Generated by [Contributors-Count]"
            "(https://github.com/Endor-Solutions-Architecture/"
            "Contributors-Count)*",
        )
        click.echo("\n".join(lines))

    else:
        click.echo("=" * 52)
        click.echo("  Cross-Platform Contributors Report")
        click.echo("=" * 52)
        click.echo(f"  Scan Date:         {now.strftime('%Y-%m-%d')}")
        click.echo(f"  Time Window:       {days} days")
        click.echo(
            f"  Bots Excluded:     {'Yes' if exclude_bots else 'No'}",
        )
        click.echo(f"  Scan Duration:     {_elapsed(elapsed)}")
        click.echo()

        for r in results:
            click.echo(f"  {r.label}")
            click.echo(f"    Repositories:    {r.repos_scanned}")
            click.echo(f"    Commits:         {r.total_commits:,}")
            click.echo(f"    Contributors:    {len(r.contributors)}")
            if r.skipped_repos:
                click.echo(
                    f"    Skipped:         {len(r.skipped_repos)} repo(s)",
                )
            click.echo()

        click.echo("-" * 52)
        if per_platform_count != unique_count:
            click.echo(f"  Per-platform sum:  {per_platform_count}")
            click.echo(
                f"  Cross-platform:    "
                f"{per_platform_count - unique_count} duplicate(s) merged",
            )
        click.echo(f"  Unique Contributors: {unique_count}")
        click.echo("=" * 52)

        if list_contributors and merged:
            click.echo("\n  Contributors:")
            for m in merged:
                platforms_str = ", ".join(
                    mi["platform"] for mi in m["members"]
                )
                emails_str = ", ".join(m["emails"]) or "N/A"
                click.echo(
                    f"    {m['display']:<30} "
                    f"[{platforms_str}] {emails_str}",
                )
            click.echo()

        if failed_platforms:
            click.echo(
                f"\n  Warning: {len(failed_platforms)} platform(s) failed:",
            )
            for p, msg in failed_platforms:
                click.echo(f"    {p}: {msg}")


if __name__ == "__main__":
    main()
