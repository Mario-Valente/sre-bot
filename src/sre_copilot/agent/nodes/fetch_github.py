"""Node for fetching recent changes from GitHub."""

import asyncio
from datetime import datetime, timedelta

import structlog

from sre_copilot.agent.state import (
    AgentState,
    CommitInfo,
    GitHubData,
    PullRequestInfo,
    ReleaseInfo,
    StateUpdate,
)
from sre_copilot.clients.github import GitHubClient
from sre_copilot.clients.protocols import GitQueryError
from sre_copilot.config import get_settings

logger = structlog.get_logger()


async def fetch_github(state: AgentState) -> StateUpdate:
    """
    Fetch recent changes from GitHub for the affected service.

    Queries recent commits, PRs, and releases to identify
    if a recent deploy might have caused the incident.

    Args:
        state: Current agent state with alert context.

    Returns:
        Updated state with GitHub data.
    """
    log = logger.bind(
        node="fetch_github",
        service=state.alert.service_name,
    )

    settings = get_settings()

    # Skip if GitHub token not configured
    if not settings.github_token:
        log.info("GitHub token not configured, skipping")
        return {
            "github": GitHubData(
                query_errors=["GitHub token not configured"],
            )
        }

    log.info("fetching recent changes from GitHub")

    client = GitHubClient()
    alert = state.alert

    # Derive repository name from service name
    # Convention: service-name -> org/service-name
    repo = _derive_repo_name(alert.service_name, settings.github_org)

    if not repo:
        log.warning("could not determine repository name")
        return {
            "github": GitHubData(
                query_errors=["Could not determine repository name"],
            )
        }

    # Define time windows
    deploy_window = alert.timestamp - timedelta(hours=settings.recent_deploy_hours)
    commit_window = alert.timestamp - timedelta(days=1)  # Last 24 hours

    # Execute queries in parallel
    commits_task = _safe_get_commits(client, repo, commit_window, log)
    prs_task = _safe_get_prs(client, repo, commit_window, log)
    release_task = _safe_get_release(client, repo, log)

    commits, prs, release = await asyncio.gather(
        commits_task,
        prs_task,
        release_task,
        return_exceptions=True,
    )

    # Process results
    query_errors = []

    # Process commits
    recent_commits = []
    if isinstance(commits, Exception):
        query_errors.append(f"commits: {str(commits)}")
    else:
        recent_commits = _parse_commits(commits)

    # Process PRs
    recent_prs = []
    if isinstance(prs, Exception):
        query_errors.append(f"prs: {str(prs)}")
    else:
        recent_prs = _parse_prs(prs)

    # Process release
    last_release = None
    if isinstance(release, Exception):
        query_errors.append(f"release: {str(release)}")
    elif release:
        last_release = _parse_release(release)

    # Check if there was a recent deploy
    has_recent_deploy = _check_recent_deploy(
        recent_commits, recent_prs, last_release, deploy_window
    )

    github_data = GitHubData(
        recent_commits=recent_commits,
        recent_prs=recent_prs,
        last_release=last_release,
        has_recent_deploy=has_recent_deploy,
        repository=repo,
        query_errors=query_errors,
    )

    log.info(
        "github data fetched",
        repo=repo,
        commits=len(recent_commits),
        prs=len(recent_prs),
        has_release=last_release is not None,
        recent_deploy=has_recent_deploy,
        errors=len(query_errors),
    )

    return {"github": github_data}


def _derive_repo_name(service_name: str, default_org: str) -> str | None:
    """
    Derive GitHub repository name from service name.

    Conventions:
    - If service_name contains '/', use as-is (org/repo format)
    - Otherwise, combine with default_org

    Args:
        service_name: Service name from alert.
        default_org: Default GitHub organization.

    Returns:
        Repository path (org/repo) or None if cannot determine.
    """
    if "/" in service_name:
        return service_name

    if default_org:
        return f"{default_org}/{service_name}"

    return None


async def _safe_get_commits(
    client: GitHubClient,
    repo: str,
    since: datetime,
    log,
) -> list[dict]:
    """Fetch commits with error handling."""
    try:
        return await client.get_recent_commits(repo, since, limit=10)
    except GitQueryError as e:
        log.warning("failed to fetch commits", error=str(e))
        raise
    except Exception as e:
        log.exception("unexpected error fetching commits")
        raise GitQueryError(f"Unexpected error: {str(e)}") from e


async def _safe_get_prs(
    client: GitHubClient,
    repo: str,
    since: datetime,
    log,
) -> list[dict]:
    """Fetch PRs with error handling."""
    try:
        return await client.get_recent_prs(repo, state="merged", since=since, limit=10)
    except GitQueryError as e:
        log.warning("failed to fetch PRs", error=str(e))
        raise
    except Exception as e:
        log.exception("unexpected error fetching PRs")
        raise GitQueryError(f"Unexpected error: {str(e)}") from e


async def _safe_get_release(
    client: GitHubClient,
    repo: str,
    log,
) -> dict | None:
    """Fetch latest release with error handling."""
    try:
        return await client.get_latest_release(repo)
    except GitQueryError as e:
        log.warning("failed to fetch release", error=str(e))
        raise
    except Exception as e:
        log.exception("unexpected error fetching release")
        raise GitQueryError(f"Unexpected error: {str(e)}") from e


def _parse_commits(raw_commits: list[dict]) -> list[CommitInfo]:
    """Parse raw commit data to CommitInfo objects."""
    commits = []
    for item in raw_commits:
        commits.append(
            CommitInfo(
                sha=item.get("sha", "")[:7],
                message=item.get("message", ""),
                author=item.get("author", "unknown"),
                timestamp=item.get("timestamp", datetime.utcnow()),
                url=item.get("url", ""),
            )
        )
    return commits


def _parse_prs(raw_prs: list[dict]) -> list[PullRequestInfo]:
    """Parse raw PR data to PullRequestInfo objects."""
    prs = []
    for item in raw_prs:
        prs.append(
            PullRequestInfo(
                number=item.get("number", 0),
                title=item.get("title", ""),
                author=item.get("author", "unknown"),
                merged_at=item.get("merged_at"),
                url=item.get("url", ""),
                files_changed=item.get("changed_files", 0),
            )
        )
    return prs


def _parse_release(raw_release: dict) -> ReleaseInfo:
    """Parse raw release data to ReleaseInfo object."""
    return ReleaseInfo(
        tag=raw_release.get("tag", ""),
        name=raw_release.get("name", ""),
        published_at=raw_release.get("published_at", datetime.utcnow()),
        url=raw_release.get("url", ""),
    )


def _check_recent_deploy(
    commits: list[CommitInfo],
    prs: list[PullRequestInfo],
    release: ReleaseInfo | None,
    deploy_window: datetime,
) -> bool:
    """
    Check if there was a recent deploy within the window.

    Considers:
    - Commits pushed recently
    - PRs merged recently
    - Release published recently
    """
    # Check commits
    for commit in commits:
        if commit.timestamp and commit.timestamp >= deploy_window:
            return True

    # Check PRs
    for pr in prs:
        if pr.merged_at and pr.merged_at >= deploy_window:
            return True

    # Check release
    return bool(release and release.published_at and release.published_at >= deploy_window)
