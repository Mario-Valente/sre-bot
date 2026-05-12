"""Pre-defined PromQL query templates for Kube State Metrics."""

from enum import StrEnum
from string import Template

from sre_copilot.queries.prometheus import _validate_label_value


class KubeMetricType(StrEnum):
    """Available Kube State Metrics types."""

    # Pod metrics
    POD_STATUS_PHASE = "pod_status_phase"
    POD_CONTAINER_STATUS_WAITING = "pod_container_status_waiting"
    POD_CONTAINER_STATUS_TERMINATED = "pod_container_status_terminated"
    POD_CONTAINER_STATUS_RESTARTS = "pod_container_status_restarts"
    POD_CONTAINER_STATUS_READY = "pod_container_status_ready"

    # Deployment metrics
    DEPLOYMENT_REPLICAS = "deployment_replicas"
    DEPLOYMENT_REPLICAS_AVAILABLE = "deployment_replicas_available"
    DEPLOYMENT_REPLICAS_UNAVAILABLE = "deployment_replicas_unavailable"
    DEPLOYMENT_CONDITION = "deployment_condition"

    # ReplicaSet metrics
    REPLICASET_REPLICAS = "replicaset_replicas"
    REPLICASET_REPLICAS_READY = "replicaset_replicas_ready"

    # Resource metrics
    POD_CONTAINER_RESOURCE_LIMITS = "pod_container_resource_limits"
    POD_CONTAINER_RESOURCE_REQUESTS = "pod_container_resource_requests"

    # Node metrics (for context)
    NODE_STATUS_CONDITION = "node_status_condition"

    # HPA metrics
    HPA_STATUS_CURRENT_REPLICAS = "hpa_status_current_replicas"
    HPA_STATUS_DESIRED_REPLICAS = "hpa_status_desired_replicas"


# ============================================================================
# KUBE STATE METRICS QUERY TEMPLATES
# These templates query kube-state-metrics exposed via Prometheus.
# ============================================================================

KUBE_STATE_TEMPLATES: dict[KubeMetricType, Template] = {
    # Pod phase (Pending, Running, Succeeded, Failed, Unknown)
    KubeMetricType.POD_STATUS_PHASE: Template(
        'kube_pod_status_phase{namespace="$namespace", pod=~"$service.*"} == 1'
    ),
    # Containers in waiting state with reason
    KubeMetricType.POD_CONTAINER_STATUS_WAITING: Template(
        'kube_pod_container_status_waiting_reason{namespace="$namespace", pod=~"$service.*"} == 1'
    ),
    # Containers in terminated state with reason
    KubeMetricType.POD_CONTAINER_STATUS_TERMINATED: Template(
        "kube_pod_container_status_terminated_reason{"
        'namespace="$namespace", '
        'pod=~"$service.*"'
        "} == 1"
    ),
    # Container restarts total
    KubeMetricType.POD_CONTAINER_STATUS_RESTARTS: Template(
        'kube_pod_container_status_restarts_total{namespace="$namespace", pod=~"$service.*"}'
    ),
    # Container ready status
    KubeMetricType.POD_CONTAINER_STATUS_READY: Template(
        'kube_pod_container_status_ready{namespace="$namespace", pod=~"$service.*"}'
    ),
    # Deployment desired replicas
    KubeMetricType.DEPLOYMENT_REPLICAS: Template(
        'kube_deployment_spec_replicas{namespace="$namespace", deployment=~"$service.*"}'
    ),
    # Deployment available replicas
    KubeMetricType.DEPLOYMENT_REPLICAS_AVAILABLE: Template(
        "kube_deployment_status_replicas_available{"
        'namespace="$namespace", '
        'deployment=~"$service.*"'
        "}"
    ),
    # Deployment unavailable replicas
    KubeMetricType.DEPLOYMENT_REPLICAS_UNAVAILABLE: Template(
        "kube_deployment_status_replicas_unavailable{"
        'namespace="$namespace", '
        'deployment=~"$service.*"'
        "}"
    ),
    # Deployment conditions (Available, Progressing, ReplicaFailure)
    KubeMetricType.DEPLOYMENT_CONDITION: Template(
        "kube_deployment_status_condition{"
        'namespace="$namespace", '
        'deployment=~"$service.*", '
        'status="true"'
        "} == 1"
    ),
    # ReplicaSet replicas
    KubeMetricType.REPLICASET_REPLICAS: Template(
        'kube_replicaset_spec_replicas{namespace="$namespace", replicaset=~"$service.*"}'
    ),
    # ReplicaSet ready replicas
    KubeMetricType.REPLICASET_REPLICAS_READY: Template(
        'kube_replicaset_status_ready_replicas{namespace="$namespace", replicaset=~"$service.*"}'
    ),
    # Container resource limits (CPU/memory)
    KubeMetricType.POD_CONTAINER_RESOURCE_LIMITS: Template(
        'kube_pod_container_resource_limits{namespace="$namespace", pod=~"$service.*"}'
    ),
    # Container resource requests (CPU/memory)
    KubeMetricType.POD_CONTAINER_RESOURCE_REQUESTS: Template(
        'kube_pod_container_resource_requests{namespace="$namespace", pod=~"$service.*"}'
    ),
    # Node conditions (Ready, MemoryPressure, DiskPressure, PIDPressure)
    KubeMetricType.NODE_STATUS_CONDITION: Template(
        "kube_node_status_condition{"
        'condition=~"Ready|MemoryPressure|DiskPressure|PIDPressure", '
        'status="true"'
        "} == 1"
    ),
    # HPA current replicas
    KubeMetricType.HPA_STATUS_CURRENT_REPLICAS: Template(
        "kube_horizontalpodautoscaler_status_current_replicas{"
        'namespace="$namespace", '
        'horizontalpodautoscaler=~"$service.*"'
        "}"
    ),
    # HPA desired replicas
    KubeMetricType.HPA_STATUS_DESIRED_REPLICAS: Template(
        "kube_horizontalpodautoscaler_status_desired_replicas{"
        'namespace="$namespace", '
        'horizontalpodautoscaler=~"$service.*"'
        "}"
    ),
}


def build_kube_state_query(
    metric_type: KubeMetricType,
    service: str,
    namespace: str,
    **extra_vars: str,
) -> str:
    """
    Build a safe PromQL query for Kube State Metrics.

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
        >>> query = build_kube_state_query(
        ...     KubeMetricType.POD_STATUS_PHASE,
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

    # Get template and substitute
    template = KUBE_STATE_TEMPLATES[metric_type]
    return template.safe_substitute(
        service=service,
        namespace=namespace,
        **extra_vars,
    )


def get_pod_health_queries(service: str, namespace: str) -> dict[str, str]:
    """
    Get all queries needed for pod health assessment.

    Args:
        service: Service name.
        namespace: Kubernetes namespace.

    Returns:
        Dictionary of query name to PromQL query.
    """
    queries = {
        "pod_phase": build_kube_state_query(KubeMetricType.POD_STATUS_PHASE, service, namespace),
        "container_waiting": build_kube_state_query(
            KubeMetricType.POD_CONTAINER_STATUS_WAITING, service, namespace
        ),
        "container_terminated": build_kube_state_query(
            KubeMetricType.POD_CONTAINER_STATUS_TERMINATED, service, namespace
        ),
        "container_restarts": build_kube_state_query(
            KubeMetricType.POD_CONTAINER_STATUS_RESTARTS, service, namespace
        ),
        "container_ready": build_kube_state_query(
            KubeMetricType.POD_CONTAINER_STATUS_READY, service, namespace
        ),
    }
    return queries


def get_deployment_health_queries(service: str, namespace: str) -> dict[str, str]:
    """
    Get all queries needed for deployment health assessment.

    Args:
        service: Service name (deployment name).
        namespace: Kubernetes namespace.

    Returns:
        Dictionary of query name to PromQL query.
    """
    queries = {
        "replicas_desired": build_kube_state_query(
            KubeMetricType.DEPLOYMENT_REPLICAS, service, namespace
        ),
        "replicas_available": build_kube_state_query(
            KubeMetricType.DEPLOYMENT_REPLICAS_AVAILABLE, service, namespace
        ),
        "replicas_unavailable": build_kube_state_query(
            KubeMetricType.DEPLOYMENT_REPLICAS_UNAVAILABLE, service, namespace
        ),
        "deployment_condition": build_kube_state_query(
            KubeMetricType.DEPLOYMENT_CONDITION, service, namespace
        ),
    }
    return queries


def get_resource_queries(service: str, namespace: str) -> dict[str, str]:
    """
    Get queries for resource limits and requests.

    Args:
        service: Service name.
        namespace: Kubernetes namespace.

    Returns:
        Dictionary of query name to PromQL query.
    """
    queries = {
        "resource_limits": build_kube_state_query(
            KubeMetricType.POD_CONTAINER_RESOURCE_LIMITS, service, namespace
        ),
        "resource_requests": build_kube_state_query(
            KubeMetricType.POD_CONTAINER_RESOURCE_REQUESTS, service, namespace
        ),
    }
    return queries
