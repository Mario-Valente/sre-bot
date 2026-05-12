"""Pre-defined TraceQL query templates for safe trace collection."""

from enum import StrEnum
from string import Template


class TraceQueryType(StrEnum):
    """Available trace query types for Tempo."""

    ERROR_TRACES = "error_traces"
    SLOW_TRACES = "slow_traces"
    FAILED_HTTP = "failed_http"
    HIGH_LATENCY = "high_latency"
    DATABASE_ERRORS = "database_errors"
    EXTERNAL_CALL_ERRORS = "external_call_errors"


# ============================================================================
# TEMPO TRACEQL TEMPLATES
# These templates are validated by SRE team. The LLM never generates TraceQL.
# ============================================================================

TEMPO_TEMPLATES: dict[TraceQueryType, Template] = {
    # Traces with error status
    TraceQueryType.ERROR_TRACES: Template('{resource.service.name="$service" && status=error}'),
    # Traces slower than threshold (default 1s)
    TraceQueryType.SLOW_TRACES: Template(
        '{resource.service.name="$service" && duration>$threshold}'
    ),
    # HTTP requests with 5xx status codes
    TraceQueryType.FAILED_HTTP: Template(
        '{resource.service.name="$service" && span.http.status_code>=500}'
    ),
    # High latency traces (P99+)
    TraceQueryType.HIGH_LATENCY: Template(
        '{resource.service.name="$service" && duration>$threshold}'
    ),
    # Database operation errors
    TraceQueryType.DATABASE_ERRORS: Template(
        '{resource.service.name="$service" && span.db.system=~".*" && status=error}'
    ),
    # External service call errors
    TraceQueryType.EXTERNAL_CALL_ERRORS: Template(
        '{resource.service.name="$service" && kind=client && status=error}'
    ),
}

# Default thresholds for different query types
DEFAULT_THRESHOLDS: dict[TraceQueryType, str] = {
    TraceQueryType.SLOW_TRACES: "1s",
    TraceQueryType.HIGH_LATENCY: "2s",
}


class TraceQueryValidationError(Exception):
    """Raised when trace query parameters fail validation."""

    pass


def build_tempo_query(
    query_type: TraceQueryType,
    service: str,
    threshold: str | None = None,
    **extra_vars: str,
) -> str:
    """
    Build a safe TraceQL query from a pre-defined template.

    All input values are validated to prevent injection attacks.

    Args:
        query_type: The type of trace query.
        service: Service name (will be sanitized).
        threshold: Duration threshold (e.g., "1s", "500ms"). Uses default if not provided.
        **extra_vars: Additional template variables.

    Returns:
        Safe TraceQL query string.

    Raises:
        TraceQueryValidationError: If any parameter fails validation.
        KeyError: If query_type is not found.

    Example:
        >>> query = build_tempo_query(
        ...     TraceQueryType.SLOW_TRACES,
        ...     service="payment-service",
        ...     threshold="500ms"
        ... )
    """
    # Validate service name
    _validate_service_name(service)

    # Get threshold with default fallback
    if threshold is None:
        threshold = DEFAULT_THRESHOLDS.get(query_type, "1s")
    else:
        _validate_duration(threshold)

    # Validate extra parameters
    for key, value in extra_vars.items():
        _validate_label_value(value, key)

    # Get template and substitute
    template = TEMPO_TEMPLATES[query_type]
    return template.safe_substitute(
        service=service,
        threshold=threshold,
        **extra_vars,
    )


def _validate_service_name(value: str) -> None:
    """
    Validate that a service name is safe for use in TraceQL.

    Args:
        value: The service name to validate.

    Raises:
        TraceQueryValidationError: If validation fails.
    """
    if not value:
        raise TraceQueryValidationError("Service name cannot be empty")

    if len(value) > 128:
        raise TraceQueryValidationError(f"Service name too long: {len(value)} chars (max 128)")

    # Forbidden characters
    forbidden = set('"{}\n\\`$|&')
    found = set(value) & forbidden
    if found:
        raise TraceQueryValidationError(f"Service name contains forbidden characters: {found}")


def _validate_duration(value: str) -> None:
    """
    Validate that a duration string is properly formatted.

    Valid formats: "1s", "500ms", "1m", "100us", "1h"

    Args:
        value: The duration string to validate.

    Raises:
        TraceQueryValidationError: If validation fails.
    """
    import re

    if not value:
        raise TraceQueryValidationError("Duration cannot be empty")

    # Pattern: number followed by unit (ns, us, ms, s, m, h)
    pattern = r"^\d+(\.\d+)?(ns|us|ms|s|m|h)$"
    if not re.match(pattern, value):
        raise TraceQueryValidationError(
            f"Invalid duration format: '{value}'. "
            "Expected format: number + unit (ns, us, ms, s, m, h). "
            "Examples: '500ms', '1s', '2m'"
        )


def _validate_label_value(value: str, name: str) -> None:
    """
    Validate that a label value is safe for use in TraceQL.

    Args:
        value: The value to validate.
        name: Parameter name for error messages.

    Raises:
        TraceQueryValidationError: If validation fails.
    """
    if not value:
        raise TraceQueryValidationError(f"Parameter '{name}' cannot be empty")

    if len(value) > 128:
        raise TraceQueryValidationError(
            f"Parameter '{name}' too long: {len(value)} chars (max 128)"
        )

    # Forbidden characters
    forbidden = set('"{}\n\\`$|&')
    found = set(value) & forbidden
    if found:
        raise TraceQueryValidationError(
            f"Parameter '{name}' contains forbidden characters: {found}"
        )


def get_incident_trace_queries(
    service: str,
    latency_threshold: str = "1s",
) -> dict[TraceQueryType, str]:
    """
    Generate standard trace queries for incident investigation.

    Returns queries most useful during incident triage:
    - ERROR_TRACES: All traces with error status
    - SLOW_TRACES: Traces exceeding latency threshold
    - FAILED_HTTP: HTTP 5xx errors
    - EXTERNAL_CALL_ERRORS: Errors in outbound calls

    Args:
        service: Service name.
        latency_threshold: Threshold for slow traces.

    Returns:
        Dictionary mapping TraceQueryType to query strings.
    """
    incident_types = [
        TraceQueryType.ERROR_TRACES,
        TraceQueryType.SLOW_TRACES,
        TraceQueryType.FAILED_HTTP,
        TraceQueryType.EXTERNAL_CALL_ERRORS,
    ]

    queries = {}
    for query_type in incident_types:
        try:
            threshold = (
                latency_threshold
                if query_type in (TraceQueryType.SLOW_TRACES, TraceQueryType.HIGH_LATENCY)
                else None
            )
            queries[query_type] = build_tempo_query(query_type, service, threshold=threshold)
        except (TraceQueryValidationError, KeyError):
            continue

    return queries
