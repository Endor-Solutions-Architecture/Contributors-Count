# Changelog

All notable changes to Contributors-Count are documented here.

## [Unreleased]

### Added
- **Documentation ecosystem**: Comprehensive README with quick start, example outputs, and FAQ. CONTRIBUTING.md, ARCHITECTURE.md, CHANGELOG.md, and GitHub issue/PR templates.
- **Verbose mode** (`--verbose` / `-v`): API diagnostics printed to stderr across all 5 scripts. Shows connection parameters, per-repo timing, scan summary, and bot filter counts.
- **Bot exclusion** (`--exclude-bots`): Heuristic bot/service account filtering added to GitLab, Bitbucket Cloud, Bitbucket Server, and Azure DevOps. (GitHub already had this.)
- **Markdown output** (`--format markdown`): Shareable report format with summary table, contributor list, and collapsible per-repository breakdown.
- **Graceful degradation**: Per-repo error handling so a single failed repo doesn't crash the scan. Skipped repos are tracked and reported in all output formats.
- **Test suite**: 113 tests covering CLI validation, contributor deduplication, bot exclusion, verbose mode, and all output formats for every platform.

### Changed
- **Configurable time window** (`--days` / `-d`): All scripts now accept a `--days` flag (default: 90) instead of being hardcoded to 90 days.
- **JSON output keys**: `contributors_90d` renamed to `unique_contributors` across all scripts for clarity when using non-90-day windows.
- **Format choices**: `--format` now accepts `text`, `json`, or `markdown` (previously only `text` and `json`).

## [1.0.0] - 2025-12-02

### Added
- Initial release with support for GitHub, GitLab, Bitbucket Cloud, Bitbucket Server, and Azure DevOps.
- 90-day contributor counting with deduplication.
- GitHub: multi-branch scanning, `--default-branch-only`, `--exclude-bots`, `--max-repos`, GitHub Enterprise Server support.
- GitLab: group and project scanning with cross-group deduplication.
- Bitbucket Cloud: workspace-level scanning with App Password auth.
- Bitbucket Server: project-level scanning with REST API 1.0.
- Azure DevOps: project-level scanning with PAT auth and continuation-token pagination.
- Text and JSON output formats.
- `--list-contributors` flag for detailed contributor listing.
