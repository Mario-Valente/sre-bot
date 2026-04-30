"""LangGraph state definitions for the SRE Copilot agent."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


def merge_lists(left: list, right: list) -> list:
    """Reducer that merges two lists (used for LangGraph state updates)."""
    return left + right


class AlertContext(BaseModel):
    """
    Extracted context from the original alert.

    Contains all relevant labels and metadata from the Alertmanager webhook
    or Slack message that triggered the investigation.
    """

    alert_name: str = Field(
        description="Name of the alert (e.g., 'HighErrorRate', 'PodCrashLooping')"
    )
    severity: Literal["critical", "warning", "info"] = Field(
        description="Alert severity level"
    )
    service_name: str = Field(description="Name of the affected service")
    cluster: str = Field(description="Kubernetes cluster name")
    namespace: str = Field(description="Kubernetes namespace")
    pod: str | None = Field(default=None, description="Specific pod name if available")
    status_code: int | None = Field(
        default=None, description="HTTP status code if relevant"
    )
    timestamp: datetime = Field(description="When the alert fired")
    raw_payload: dict = Field(
        default_factory=dict, description="Original alert payload for debugging"
    )
    description: str = Field(default="", description="Alert description/summary")
    runbook_url: str | None = Field(
        default=None, description="Link to runbook if available"
    )


class MetricPoint(BaseModel):
    """Single metric data point."""

    timestamp: float = Field(description="Unix timestamp")
    value: float = Field(description="Metric value")


class MetricSeries(BaseModel):
    """Time series data with labels."""

    labels: dict[str, str] = Field(default_factory=dict, description="Metric labels")
    values: list[MetricPoint] = Field(
        default_factory=list, description="Time series values"
    )


class MetricsData(BaseModel):
    """
    Results from Prometheus queries.

    Contains CPU, memory, error rate, and latency metrics
    for the affected service in the alert time window.
    """

    cpu_usage: list[MetricSeries] = Field(
        default_factory=list, description="CPU usage time series"
    )
    memory_usage: list[MetricSeries] = Field(
        default_factory=list, description="Memory usage time series"
    )
    error_rate_5xx: list[MetricSeries] = Field(
        default_factory=list, description="HTTP 5xx error rate"
    )
    latency_p99: list[MetricSeries] = Field(
        default_factory=list, description="P99 latency time series"
    )
    request_rate: list[MetricSeries] = Field(
        default_factory=list, description="Request rate time series"
    )
    anomalies_detected: list[str] = Field(
        default_factory=list,
        description="Human-readable anomaly descriptions",
    )
    query_errors: list[str] = Field(
        default_factory=list, description="Errors encountered during metric queries"
    )


class LogEntry(BaseModel):
    """Single log entry from Loki."""

    timestamp: datetime = Field(description="Log timestamp")
    level: str = Field(description="Log level (error, fatal, warn, etc.)")
    message: str = Field(description="Log message content")
    labels: dict[str, str] = Field(default_factory=dict, description="Log labels")


class LogsData(BaseModel):
    """
    Results from Loki queries.

    Contains error and fatal logs for the affected service
    during the alert time window.
    """

    error_logs: list[LogEntry] = Field(
        default_factory=list, description="Logs with level=error"
    )
    fatal_logs: list[LogEntry] = Field(
        default_factory=list, description="Logs with level=fatal"
    )
    log_patterns: list[str] = Field(
        default_factory=list,
        description="Frequently occurring error patterns",
    )
    total_error_count: int = Field(default=0, description="Total error log count")
    query_errors: list[str] = Field(
        default_factory=list, description="Errors encountered during log queries"
    )


class SpanInfo(BaseModel):
    """Information about a trace span."""

    trace_id: str = Field(description="Trace ID")
    span_id: str = Field(description="Span ID")
    service_name: str = Field(description="Service that generated this span")
    operation_name: str = Field(description="Operation/endpoint name")
    duration_ms: float = Field(description="Span duration in milliseconds")
    status: str = Field(description="Span status (ok, error)")
    error_message: str | None = Field(default=None, description="Error message if any")
    timestamp: datetime = Field(description="Span start time")


class TracesData(BaseModel):
    """
    Results from Tempo queries.

    Contains traces with errors or high latency for the
    affected service during the alert time window.
    """

    failed_traces: list[SpanInfo] = Field(
        default_factory=list, description="Traces with error status"
    )
    slow_traces: list[SpanInfo] = Field(
        default_factory=list, description="Traces exceeding latency threshold"
    )
    bottleneck_services: list[str] = Field(
        default_factory=list,
        description="Services identified as bottlenecks in traces",
    )
    query_errors: list[str] = Field(
        default_factory=list, description="Errors encountered during trace queries"
    )


class CommitInfo(BaseModel):
    """Information about a Git commit."""

    sha: str = Field(description="Commit SHA")
    message: str = Field(description="Commit message")
    author: str = Field(description="Commit author")
    timestamp: datetime = Field(description="Commit timestamp")
    url: str = Field(description="URL to view commit")


class PullRequestInfo(BaseModel):
    """Information about a pull request."""

    number: int = Field(description="PR number")
    title: str = Field(description="PR title")
    author: str = Field(description="PR author")
    merged_at: datetime | None = Field(default=None, description="Merge timestamp")
    url: str = Field(description="URL to view PR")
    files_changed: int = Field(default=0, description="Number of files changed")


class ReleaseInfo(BaseModel):
    """Information about a release."""

    tag: str = Field(description="Release tag")
    name: str = Field(description="Release name")
    published_at: datetime = Field(description="Release timestamp")
    url: str = Field(description="URL to view release")


class GitHubData(BaseModel):
    """
    Recent changes from GitHub repository.

    Used to correlate incidents with recent deployments,
    code changes, or releases.
    """

    recent_commits: list[CommitInfo] = Field(
        default_factory=list, description="Recent commits to main branch"
    )
    recent_prs: list[PullRequestInfo] = Field(
        default_factory=list, description="Recently merged PRs"
    )
    last_release: ReleaseInfo | None = Field(
        default=None, description="Most recent release"
    )
    has_recent_deploy: bool = Field(
        default=False,
        description="Whether a deploy occurred within the recent deploy window",
    )
    repository: str = Field(default="", description="Repository name")
    query_errors: list[str] = Field(
        default_factory=list, description="Errors encountered during GitHub queries"
    )


class IncidentAnalysis(BaseModel):
    """
    Final analysis synthesized by the LLM.

    Consolidates all collected data into a root cause hypothesis
    with supporting evidence and recommended actions.
    """

    summary: str = Field(
        description="Brief TL;DR of the incident (1-2 sentences)",
    )
    probable_root_cause: str = Field(
        description="Primary hypothesis for the root cause",
    )
    contributing_factors: list[str] = Field(
        default_factory=list,
        description="Secondary factors that may have contributed",
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Data points that support the hypothesis",
    )
    suggested_actions: list[str] = Field(
        default_factory=list,
        description="Recommended next steps for mitigation",
    )
    confidence: Literal["high", "medium", "low"] = Field(
        description="Confidence level in the analysis",
    )
    needs_human_escalation: bool = Field(
        default=False,
        description="Whether this incident requires immediate human attention",
    )
    escalation_reason: str | None = Field(
        default=None,
        description="Reason for escalation if needed",
    )


class AgentState(BaseModel):
    """
    Main state that flows through the LangGraph.

    This state is passed between nodes and accumulates data
    as the investigation progresses.
    """

    # === Input ===
    alert: AlertContext = Field(description="Extracted alert context")

    # === Collected Data (populated by nodes) ===
    metrics: MetricsData | None = Field(
        default=None, description="Prometheus metrics data"
    )
    logs: LogsData | None = Field(default=None, description="Loki logs data")
    traces: TracesData | None = Field(default=None, description="Tempo traces data")
    github: GitHubData | None = Field(default=None, description="GitHub changes data")

    # === Output ===
    analysis: IncidentAnalysis | None = Field(
        default=None, description="Final synthesized analysis"
    )

    # === Slack Metadata ===
    slack_thread_ts: str | None = Field(
        default=None, description="Slack thread timestamp for replies"
    )
    slack_channel: str | None = Field(
        default=None, description="Slack channel ID for posting"
    )
    slack_message_ts: str | None = Field(
        default=None, description="Timestamp of the bot's response message"
    )

    # === Execution Metadata ===
    errors: Annotated[list[str], merge_lists] = Field(
        default_factory=list,
        description="Errors accumulated during execution",
    )
    started_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the investigation started",
    )
    completed_at: datetime | None = Field(
        default=None, description="When the investigation completed"
    )


# Type alias for node return values (partial state updates)
StateUpdate = dict
