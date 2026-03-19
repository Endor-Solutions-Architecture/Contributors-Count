# Changelog

All notable changes to Contributors-Count are documented here.

## [Unreleased]

### Added
- **Unified cross-platform mode** (`contributors_count.py`): Scan multiple platforms in a single command with cross-platform deduplication via union-find on shared email addresses. Driven by a JSON config file.
- **Documentation ecosystem**: Comprehensive README, CONTRIBUTING.md, ARCHITECTURE.md, CHANGELOG.md, and GitHub issue/PR templates.
- **Verbose mode** (`--verbose` / `-v`): API diagnostics on stderr across all scripts.
- **Bot exclusion** (`--exclude-bots`): Heuristic filtering for all platforms (GitHub already had this).
- **Markdown output** (`--format markdown`): Shareable report format with tables and collapsible per-repo breakdowns.
- **Graceful degradation**: Per-repo error handling with skipped repo tracking in all output formats.
- **Test suite**: 134 tests covering CLI validation, deduplication, bot exclusion, verbose mode, output formats, cross-platform dedup, and unified runner.

### Changed
- **Configurable time window** (`--days` / `-d`): All scripts accept a `--days` flag (default: 90).
- **JSON output keys**: `contributors_90d` renamed to `unique_contributors`.
- **Format choices**: `--format` now accepts `text`, `json`, or `markdown`.

## [1.0.0] - 2025-12-02

### Added
- Initial release with GitHub, GitLab, Bitbucket Cloud, Bitbucket Server, and Azure DevOps support.
- 90-day contributor counting with per-platform deduplication.
- Text and JSON output formats.
- `--list-contributors` flag for detailed contributor listing.
