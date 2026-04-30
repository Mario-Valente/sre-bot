"""Abstract interfaces (Protocols) for observability clients."""

from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MetricsClient(Protocol):
    """
    Interface for metrics backends (Prometheus, Victoria Metrics, Mimir).

    Implementations must provide methods for instant and range queries.
    """

    async def query(self, query: str) -> list[dict[str, Any]]:
        """
        Execute an instant query.

        Args:
            query: PromQL/compatible query string.

        Returns:
            List of metric series with their current values.

        Raises:
            MetricsQueryError: If the query fails.
        """
        ...

    async def query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = "15s",
    ) -> list[dict[str, Any]]:
        """
        Execute a range query over a time window.

        Args:
            query: PromQL/compatible query string.
            start: Start of the time range.
            end: End of the time range.
            step: Query resolution step (default: 15s).

        Returns:
            List of metric series with time series values.

        Raises:
            MetricsQueryError: If the query fails.
        """
        ...


@runtime_checkable
class LogsClient(Protocol):
    """
    Interface for log backends (Loki, Elasticsearch).

    Implementations must provide a method for querying logs.
    """

    async def query(
        self,
        query: str,
        start: datetime,
        end: datetime,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """
        Execute a log query.

        Args:
            query: LogQL/compatible query string.
            start: Start of the time range.
            end: End of the time range.
            limit: Maximum number of log entries to return.

        Returns:
            List of log entries with timestamps and labels.

        Raises:
            LogsQueryError: If the query fails.
        """
        ...


@runtime_checkable
class TracesClient(Protocol):
    """
    Interface for trace backends (Tempo, Jaeger).

    Implementations must provide methods for searching and fetching traces.
    """

    async def search(
        self,
        service_name: str,
        start: datetime,
        end: datetime,
        min_duration: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Search for traces matching criteria.

        Args:
            service_name: Name of the service to search.
            start: Start of the time range.
            end: End of the time range.
            min_duration: Minimum trace duration (e.g., "100ms").
            status: Filter by status ("error", "ok").
            limit: Maximum number of traces to return.

        Returns:
            List of trace summaries.

        Raises:
            TracesQueryError: If the search fails.
        """
        ...

    async def get_trace(self, trace_id: str) -> dict[str, Any]:
        """
        Fetch a specific trace by ID.

        Args:
            trace_id: The trace ID to fetch.

        Returns:
            Full trace data with all spans.

        Raises:
            TracesQueryError: If the trace cannot be fetched.
        """
        ...


@runtime_checkable
class GitClient(Protocol):
    """
    Interface for Git providers (GitHub, GitLab).

    Implementations must provide methods for fetching recent activity.
    """

    async def get_recent_commits(
        self,
        repo: str,
        since: datetime,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        List recent commits on the default branch.

        Args:
            repo: Repository name (e.g., "org/repo").
            since: Only include commits after this time.
            limit: Maximum number of commits to return.

        Returns:
            List of commit information.

        Raises:
            GitQueryError: If the query fails.
        """
        ...

    async def get_recent_prs(
        self,
        repo: str,
        state: str = "merged",
        since: datetime | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        List recent pull requests.

        Args:
            repo: Repository name (e.g., "org/repo").
            state: PR state filter ("merged", "open", "closed").
            since: Only include PRs after this time.
            limit: Maximum number of PRs to return.

        Returns:
            List of pull request information.

        Raises:
            GitQueryError: If the query fails.
        """
        ...

    async def get_latest_release(self, repo: str) -> dict[str, Any] | None:
        """
        Fetch the most recent release.

        Args:
            repo: Repository name (e.g., "org/repo").

        Returns:
            Release information, or None if no releases exist.

        Raises:
            GitQueryError: If the query fails.
        """
        ...


# === Exceptions ===


class ObservabilityError(Exception):
    """Base exception for observability client errors."""

    pass


class MetricsQueryError(ObservabilityError):
    """Error executing a metrics query."""

    pass


class LogsQueryError(ObservabilityError):
    """Error executing a logs query."""

    pass


class TracesQueryError(ObservabilityError):
    """Error executing a traces query."""

    pass


class GitQueryError(ObservabilityError):
    """Error querying Git provider."""

    pass
