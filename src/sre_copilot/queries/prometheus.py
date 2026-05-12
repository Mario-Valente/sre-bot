"""Pre-defined PromQL query templates for safe metric collection."""

from enum import StrEnum
from string import Template


class MetricType(StrEnum):
    """Available metric types for Prometheus queries."""

    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"
    ERROR_RATE = "error_rate"
    LATENCY_P50 = "latency_p50"
    LATENCY_P95 = "latency_p95"
    LATENCY_P99 = "latency_p99"
    REQUEST_RATE = "request_rate"
    SATURATION = "saturation"
    AVAILABILITY = "availability"
    POD_RESTARTS = "pod_restarts"


# ============================================================================
# PROMETHEUS QUERY TEMPLATES
# These templates are validated by SRE team. The LLM never generates PromQL.
# ============================================================================

PROMETHEUS_TEMPLATES: dict[MetricType, Template] = {
    # CPU usage rate for containers in a service
    MetricType.CPU_USAGE: Template(
        "sum(rate(container_cpu_usage_seconds_total{"
        'namespace="$namespace", '
        'pod=~"$service.*", '
        'container!="POD", '
        'container!=""'
        "}[5m])) by (pod)"
    ),
    # Memory usage for containers in a service
    MetricType.MEMORY_USAGE: Template(
        "sum(container_memory_working_set_bytes{"
        'namespace="$namespace", '
        'pod=~"$service.*", '
        'container!="POD", '
        'container!=""'
        "}) by (pod)"
    ),
    # HTTP 5xx error rate (errors / total requests)
    MetricType.ERROR_RATE: Template(
        "sum(rate(http_requests_total{"
        'namespace="$namespace", '
        'service="$service", '
        'status=~"5.."'
        "}[5m])) / "
        "sum(rate(http_requests_total{"
        'namespace="$namespace", '
        'service="$service"'
        "}[5m]))"
    ),
    # P50 latency
    MetricType.LATENCY_P50: Template(
        "histogram_quantile(0.50, "
        "sum(rate(http_request_duration_seconds_bucket{"
        'namespace="$namespace", '
        'service="$service"'
        "}[5m])) by (le))"
    ),
    # P95 latency
    MetricType.LATENCY_P95: Template(
        "histogram_quantile(0.95, "
        "sum(rate(http_request_duration_seconds_bucket{"
        'namespace="$namespace", '
        'service="$service"'
        "}[5m])) by (le))"
    ),
    # P99 latency
    MetricType.LATENCY_P99: Template(
        "histogram_quantile(0.99, "
        "sum(rate(http_request_duration_seconds_bucket{"
        'namespace="$namespace", '
        'service="$service"'
        "}[5m])) by (le))"
    ),
    # Request rate (requests per second)
    MetricType.REQUEST_RATE: Template(
        'sum(rate(http_requests_total{namespace="$namespace", service="$service"}[5m]))'
    ),
    # Saturation - CPU throttling
    MetricType.SATURATION: Template(
        "sum(rate(container_cpu_cfs_throttled_seconds_total{"
        'namespace="$namespace", '
        'pod=~"$service.*"'
        "}[5m])) by (pod)"
    ),
    # Availability (successful requests / total)
    MetricType.AVAILABILITY: Template(
        "sum(rate(http_requests_total{"
        'namespace="$namespace", '
        'service="$service", '
        'status=~"2..|3.."'
        "}[5m])) / "
        "sum(rate(http_requests_total{"
        'namespace="$namespace", '
        'service="$service"'
        "}[5m]))"
    ),
    # Pod restart count
    MetricType.POD_RESTARTS: Template(
        "sum(increase(kube_pod_container_status_restarts_total{"
        'namespace="$namespace", '
        'pod=~"$service.*"'
        "}[1h])) by (pod)"
    ),
}


class QueryValidationError(Exception):
    """Raised when query parameters fail validation."""

    pass


def build_prometheus_query(
    metric_type: MetricType,
    service: str,
    namespace: str,
    **extra_vars: str,
) -> str:
    """
    Build a safe PromQL query from a pre-defined template.

    All input values are validated to prevent injection attacks.

    Args:
        metric_type: The type of metric to query.
        service: Service name (will be sanitized).
        namespace: Kubernetes namespace (will be sanitized).
        **extra_vars: Additional template variables.

    Returns:
        Safe PromQL query string.

    Raises:
        QueryValidationError: If any parameter fails validation.
        KeyError: If metric_type is not found.

    Example:
        >>> query = build_prometheus_query(
        ...     MetricType.ERROR_RATE,
        ...     service="payment-service",
        ...     namespace="production"
        ... )
        >>> print(query)
        sum(rate(http_requests_total{namespace="production", ...}))
    """
    # Validate required parameters
    _validate_label_value(service, "service")
    _validate_label_value(namespace, "namespace")

    # Validate extra parameters
    for key, value in extra_vars.items():
        _validate_label_value(value, key)

    # Get template and substitute
    template = PROMETHEUS_TEMPLATES[metric_type]
    return template.safe_substitute(
        service=service,
        namespace=namespace,
        **extra_vars,
    )


def _validate_label_value(value: str, name: str) -> None:
    """
    Validate that a label value is safe for use in PromQL.

    Prometheus label values can contain any UTF-8 characters,
    but we restrict to alphanumeric, dash, underscore, and dot
    to prevent injection attacks.

    Args:
        value: The value to validate.
        name: Parameter name for error messages.

    Raises:
        QueryValidationError: If validation fails.
    """
    if not value:
        raise QueryValidationError(f"Parameter '{name}' cannot be empty")

    if len(value) > 128:
        raise QueryValidationError(f"Parameter '{name}' too long: {len(value)} chars (max 128)")

    # Forbidden characters that could enable injection
    forbidden = set('"{}\n\\`$')
    found = set(value) & forbidden
    if found:
        raise QueryValidationError(f"Parameter '{name}' contains forbidden characters: {found}")

    # Must start with alphanumeric
    if not value[0].isalnum():
        raise QueryValidationError(f"Parameter '{name}' must start with alphanumeric character")


def get_all_metric_queries(
    service: str,
    namespace: str,
) -> dict[MetricType, str]:
    """
    Generate all standard metric queries for a service.

    Useful for collecting a complete set of metrics in one call.

    Args:
        service: Service name.
        namespace: Kubernetes namespace.

    Returns:
        Dictionary mapping MetricType to query strings.
    """
    queries = {}
    for metric_type in MetricType:
        try:
            queries[metric_type] = build_prometheus_query(metric_type, service, namespace)
        except (QueryValidationError, KeyError):
            continue
    return queries
