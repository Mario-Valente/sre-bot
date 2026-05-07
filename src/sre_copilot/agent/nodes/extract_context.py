"""Node for extracting context from incoming alerts."""

from datetime import datetime

import structlog

from sre_copilot.agent.state import AgentState, AlertContext, StateUpdate

logger = structlog.get_logger()


async def extract_context(state: AgentState) -> StateUpdate:
    """
    Extract and validate alert context.

    This is the first node in the graph. It validates the incoming
    alert data and enriches it with any missing fields.

    Args:
        state: Current agent state with alert data.

    Returns:
        Updated state with validated alert context.
    """
    log = logger.bind(node="extract_context", alert_name=state.alert.alert_name)
    log.info("extracting alert context")

    try:
        alert = state.alert

        # Validate required fields
        errors = []
        if not alert.service_name:
            errors.append("Missing required field: service_name")
        if not alert.namespace:
            errors.append("Missing required field: namespace")

        if errors:
            log.warning("alert validation failed", errors=errors)
            return {"errors": errors}

        # Enrich context if needed
        enriched_alert = _enrich_alert(alert)

        log.info(
            "context extracted successfully",
            service=enriched_alert.service_name,
            namespace=enriched_alert.namespace,
            severity=enriched_alert.severity,
        )

        return {"alert": enriched_alert}

    except Exception as e:
        log.exception("failed to extract context")
        return {"errors": [f"Context extraction failed: {str(e)}"]}


def _enrich_alert(alert: AlertContext) -> AlertContext:
    """
    Enrich alert with derived or default values.

    Args:
        alert: Original alert context.

    Returns:
        Enriched alert context.
    """
    # Create a copy with enrichments
    enriched = alert.model_copy()

    # Ensure timestamp is set
    if not enriched.timestamp:
        enriched.timestamp = datetime.utcnow()

    # Extract additional info from raw payload if available
    raw = enriched.raw_payload
    if raw:
        # Try to get description from common alert fields
        if not enriched.description:
            enriched.description = (
                raw.get("annotations", {}).get("description", "")
                or raw.get("annotations", {}).get("summary", "")
                or raw.get("description", "")
            )

        # Try to get runbook URL
        if not enriched.runbook_url:
            enriched.runbook_url = raw.get("annotations", {}).get("runbook_url")

        # Extract pod name from labels if not set
        if not enriched.pod:
            labels = raw.get("labels", {})
            enriched.pod = labels.get("pod") or labels.get("pod_name")

    if not enriched.cluster:
        enriched.cluster = "unknown"

    return enriched


def parse_alertmanager_payload(payload: dict) -> AlertContext:
    """
    Parse an Alertmanager webhook payload into AlertContext.

    Args:
        payload: Raw Alertmanager webhook JSON.

    Returns:
        Parsed AlertContext.

    Example payload:
        {
            "alerts": [{
                "status": "firing",
                "labels": {
                    "alertname": "HighErrorRate",
                    "severity": "critical",
                    "service": "payment-api",
                    "namespace": "production",
                    "cluster": "main"
                },
                "annotations": {
                    "summary": "High error rate detected",
                    "description": "Error rate > 5%"
                },
                "startsAt": "2024-01-01T00:00:00Z"
            }]
        }
    """
    # Get the first firing alert
    alerts = payload.get("alerts", [])
    alert_data = next(
        (a for a in alerts if a.get("status") == "firing"),
        alerts[0] if alerts else {},
    )

    labels = alert_data.get("labels", {})
    common_labels = payload.get("commonLabels", {})
    group_labels = payload.get("groupLabels", {})
    annotations = alert_data.get("annotations", {})
    common_annotations = payload.get("commonAnnotations", {})

    def _annotation(name: str, default: str = "") -> str:
        return annotations.get(name) or common_annotations.get(name) or default

    def _label(name: str, default: str = "") -> str:
        return (
            labels.get(name)
            or common_labels.get(name)
            or group_labels.get(name)
            or default
        )

    # Parse timestamp
    starts_at = alert_data.get("startsAt", "")
    timestamp = datetime.utcnow()
    if starts_at:
        try:
            timestamp = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
        except ValueError:
            pass

    # Map severity
    severity_raw = _label("severity", "warning").lower()
    severity = "critical" if severity_raw == "critical" else (
        "warning" if severity_raw == "warning" else "info"
    )

    return AlertContext(
        alert_name=_label("alertname", "UnknownAlert"),
        severity=severity,
        service_name=_label("service") or _label("service_name"),
        cluster=_label("cluster"),
        namespace=_label("namespace"),
        pod=_label("pod") or _label("pod_name") or None,
        status_code=_safe_int(_label("status_code") or None),
        timestamp=timestamp,
        description=_annotation("description") or _annotation("summary"),
        runbook_url=_annotation("runbook_url") or None,
        raw_payload=payload,
    )


def _safe_int(value: str | None) -> int | None:
    """Safely convert string to int."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
