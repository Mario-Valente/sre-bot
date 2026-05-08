"""Pre-defined LogQL query templates for safe log collection."""

from enum import Enum
from string import Template


class LogQueryType(str, Enum):
    """Available log query types for Loki."""

    ERROR_LOGS = "error_logs"
    FATAL_LOGS = "fatal_logs"
    WARN_LOGS = "warn_logs"
    ALL_ERRORS = "all_errors"  # error + fatal
    EXCEPTION_LOGS = "exception_logs"
    TIMEOUT_LOGS = "timeout_logs"
    CONNECTION_LOGS = "connection_logs"
    OOM_LOGS = "oom_logs"


# ============================================================================
# LOKI QUERY TEMPLATES
# These templates are validated by SRE team. The LLM never generates LogQL.
# ============================================================================

LOKI_TEMPLATES: dict[LogQueryType, Template] = {
    # Error level logs
    LogQueryType.ERROR_LOGS: Template(
        '{namespace="$namespace", app="$service"} |= "level" | json | level="error"'
    ),
    # Fatal level logs
    LogQueryType.FATAL_LOGS: Template(
        '{namespace="$namespace", app="$service"} |= "level" | json | level="fatal"'
    ),
    # Warning level logs
    LogQueryType.WARN_LOGS: Template(
        '{namespace="$namespace", app="$service"} |= "level" | json | level=~"warn|warning"'
    ),
    # All error and fatal logs combined
    LogQueryType.ALL_ERRORS: Template(
        '{namespace="$namespace", app="$service"} |= "level" | json | level=~"error|fatal"'
    ),
    # Logs containing exception/stack traces
    LogQueryType.EXCEPTION_LOGS: Template(
        '{namespace="$namespace", app="$service"} |~ "(?i)(exception|stacktrace|traceback|panic)"'
    ),
    # Timeout related logs
    LogQueryType.TIMEOUT_LOGS: Template(
        '{namespace="$namespace", app="$service"} |~ "(?i)(timeout|timed out|deadline exceeded)"'
    ),
    # Connection error logs
    LogQueryType.CONNECTION_LOGS: Template(
        '{namespace="$namespace", app="$service"} '
        '|~ "(?i)(connection refused|connection reset|ECONNREFUSED|ECONNRESET|no route to host)"'
    ),
    # Out of memory logs
    LogQueryType.OOM_LOGS: Template(
        '{namespace="$namespace", app="$service"} '
        '|~ "(?i)(out of memory|OOMKilled|memory limit|heap space)"'
    ),
}

# Alternative templates for different label schemas
LOKI_TEMPLATES_ALT: dict[LogQueryType, Template] = {
    # Some clusters use "service" label instead of "app"
    LogQueryType.ERROR_LOGS: Template(
        '{namespace="$namespace", service="$service"} |= "level" | json | level="error"'
    ),
    LogQueryType.FATAL_LOGS: Template(
        '{namespace="$namespace", service="$service"} |= "level" | json | level="fatal"'
    ),
    LogQueryType.ALL_ERRORS: Template(
        '{namespace="$namespace", service="$service"} |= "level" | json | level=~"error|fatal"'
    ),
}


class LogQueryValidationError(Exception):
    """Raised when log query parameters fail validation."""

    pass


def build_loki_query(
    query_type: LogQueryType,
    service: str,
    namespace: str,
    use_alt_labels: bool = False,
    **extra_vars: str,
) -> str:
    """
    Build a safe LogQL query from a pre-defined template.

    All input values are validated to prevent injection attacks.

    Args:
        query_type: The type of log query.
        service: Service name (will be sanitized).
        namespace: Kubernetes namespace (will be sanitized).
        use_alt_labels: Use alternative label schema (service vs app).
        **extra_vars: Additional template variables.

    Returns:
        Safe LogQL query string.

    Raises:
        LogQueryValidationError: If any parameter fails validation.
        KeyError: If query_type is not found.

    Example:
        >>> query = build_loki_query(
        ...     LogQueryType.ERROR_LOGS,
        ...     service="payment-service",
        ...     namespace="production"
        ... )
    """
    # Validate required parameters
    _validate_label_value(service, "service")
    _validate_label_value(namespace, "namespace")

    # Validate extra parameters
    for key, value in extra_vars.items():
        _validate_label_value(value, key)

    # Get template
    templates = LOKI_TEMPLATES_ALT if use_alt_labels else LOKI_TEMPLATES
    if query_type not in templates:
        templates = LOKI_TEMPLATES  # Fall back to primary

    template = templates[query_type]
    return template.safe_substitute(
        service=service,
        namespace=namespace,
        **extra_vars,
    )


def _validate_label_value(value: str, name: str) -> None:
    """
    Validate that a label value is safe for use in LogQL.

    Args:
        value: The value to validate.
        name: Parameter name for error messages.

    Raises:
        LogQueryValidationError: If validation fails.
    """
    if not value:
        raise LogQueryValidationError(f"Parameter '{name}' cannot be empty")

    if len(value) > 128:
        raise LogQueryValidationError(f"Parameter '{name}' too long: {len(value)} chars (max 128)")

    # Forbidden characters that could enable injection
    forbidden = set('"{}\n\\`$|')
    found = set(value) & forbidden
    if found:
        raise LogQueryValidationError(f"Parameter '{name}' contains forbidden characters: {found}")


def get_incident_log_queries(
    service: str,
    namespace: str,
    use_alt_labels: bool = False,
) -> dict[LogQueryType, str]:
    """
    Generate standard log queries for incident investigation.

    Returns queries most useful during incident triage:
    - ALL_ERRORS: All error and fatal logs
    - EXCEPTION_LOGS: Stack traces and exceptions
    - TIMEOUT_LOGS: Timeout-related errors
    - CONNECTION_LOGS: Network/connection issues
    - OOM_LOGS: Memory issues

    Args:
        service: Service name.
        namespace: Kubernetes namespace.
        use_alt_labels: Use alternative label schema.

    Returns:
        Dictionary mapping LogQueryType to query strings.
    """
    incident_types = [
        LogQueryType.ALL_ERRORS,
        LogQueryType.EXCEPTION_LOGS,
        LogQueryType.TIMEOUT_LOGS,
        LogQueryType.CONNECTION_LOGS,
        LogQueryType.OOM_LOGS,
    ]

    queries = {}
    for query_type in incident_types:
        try:
            queries[query_type] = build_loki_query(query_type, service, namespace, use_alt_labels)
        except (LogQueryValidationError, KeyError):
            continue

    return queries
