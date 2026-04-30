"""Webhook receiver for Alertmanager alerts using FastAPI."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import structlog
import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from sre_copilot.agent.graph import run_investigation
from sre_copilot.agent.nodes.extract_context import parse_alertmanager_payload
from sre_copilot.agent.state import AgentState
from sre_copilot.config import get_settings

logger = structlog.get_logger()


class AlertmanagerWebhook(BaseModel):
    """Alertmanager webhook payload structure."""

    version: str = "4"
    groupKey: str = ""
    truncatedAlerts: int = 0
    status: str = "firing"
    receiver: str = ""
    groupLabels: dict[str, str] = {}
    commonLabels: dict[str, str] = {}
    commonAnnotations: dict[str, str] = {}
    externalURL: str = ""
    alerts: list[dict[str, Any]] = []


class WebhookResponse(BaseModel):
    """Response for webhook requests."""

    status: str
    message: str
    investigation_id: str | None = None


class HealthResponse(BaseModel):
    """Response for health check."""

    status: str
    version: str
    timestamp: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    log = logger.bind(component="webhook_server")
    log.info("webhook server starting")
    yield
    log.info("webhook server shutting down")


def create_webhook_app() -> FastAPI:
    """
    Create and configure the FastAPI webhook receiver.

    Returns:
        Configured FastAPI app.
    """
    app = FastAPI(
        title="SRE Copilot Webhook",
        description="Webhook receiver for Alertmanager alerts",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Register routes
    _register_routes(app)

    return app


def _register_routes(app: FastAPI) -> None:
    """Register all webhook routes."""

    @app.get("/health", response_model=HealthResponse)
    async def health_check() -> HealthResponse:
        """Health check endpoint."""
        return HealthResponse(
            status="healthy",
            version="0.1.0",
            timestamp=datetime.utcnow().isoformat(),
        )

    @app.get("/ready")
    async def readiness_check() -> dict:
        """Readiness check endpoint."""
        # Could add checks for dependencies (Prometheus, Loki, etc.)
        return {"status": "ready"}

    @app.post("/webhook/alertmanager", response_model=WebhookResponse)
    async def receive_alertmanager_webhook(
        webhook: AlertmanagerWebhook,
        background_tasks: BackgroundTasks,
        request: Request,
    ) -> WebhookResponse:
        """
        Receive and process Alertmanager webhooks.

        This endpoint receives alerts from Alertmanager and triggers
        investigation for critical alerts.
        """
        log = logger.bind(
            handler="alertmanager_webhook",
            status=webhook.status,
            alerts_count=len(webhook.alerts),
            group_key=webhook.groupKey,
        )

        log.info("received alertmanager webhook")

        # Only process firing alerts
        if webhook.status != "firing":
            log.debug("ignoring non-firing alert")
            return WebhookResponse(
                status="ignored",
                message=f"Alert status '{webhook.status}' ignored",
            )

        # Filter for critical alerts
        critical_alerts = [
            a for a in webhook.alerts
            if a.get("labels", {}).get("severity") == "critical"
            and a.get("status") == "firing"
        ]

        if not critical_alerts:
            log.debug("no critical firing alerts")
            return WebhookResponse(
                status="ignored",
                message="No critical firing alerts to process",
            )

        # Generate investigation ID
        investigation_id = f"inv-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        # Process each critical alert
        for alert in critical_alerts:
            background_tasks.add_task(
                _process_alert,
                alert,
                webhook.model_dump(),
                investigation_id,
            )

        log.info(
            "investigations triggered",
            count=len(critical_alerts),
            investigation_id=investigation_id,
        )

        return WebhookResponse(
            status="accepted",
            message=f"Processing {len(critical_alerts)} critical alert(s)",
            investigation_id=investigation_id,
        )

    @app.post("/webhook/custom")
    async def receive_custom_webhook(
        request: Request,
        background_tasks: BackgroundTasks,
    ) -> WebhookResponse:
        """
        Receive custom webhook payloads.

        Supports custom alert formats with required fields:
        - service_name
        - severity
        - namespace (optional, defaults to "production")
        """
        log = logger.bind(handler="custom_webhook")

        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        # Validate required fields
        if "service_name" not in payload:
            raise HTTPException(
                status_code=400,
                detail="Missing required field: service_name",
            )

        if "severity" not in payload:
            raise HTTPException(
                status_code=400,
                detail="Missing required field: severity",
            )

        log.info(
            "received custom webhook",
            service=payload.get("service_name"),
            severity=payload.get("severity"),
        )

        investigation_id = f"inv-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        background_tasks.add_task(
            _process_custom_alert,
            payload,
            investigation_id,
        )

        return WebhookResponse(
            status="accepted",
            message="Processing alert",
            investigation_id=investigation_id,
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """Handle uncaught exceptions."""
        logger.exception("unhandled exception in webhook handler")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Internal server error"},
        )


async def _process_alert(
    alert: dict,
    full_payload: dict,
    investigation_id: str,
) -> None:
    """
    Process a single alert in the background.

    Args:
        alert: Single alert from Alertmanager.
        full_payload: Complete webhook payload.
        investigation_id: Unique ID for this investigation.
    """
    log = logger.bind(
        handler="alert_processor",
        investigation_id=investigation_id,
        alert_name=alert.get("labels", {}).get("alertname"),
    )

    try:
        # Parse alert into context
        alert_context = parse_alertmanager_payload({"alerts": [alert]})

        log.info(
            "starting investigation",
            service=alert_context.service_name,
            namespace=alert_context.namespace,
        )

        # Create initial state
        settings = get_settings()
        initial_state = AgentState(
            alert=alert_context,
            slack_channel=settings.slack_alert_channel if settings.slack_bot_token else None,
        )

        # Run investigation
        final_state = await run_investigation(initial_state)

        log.info(
            "investigation completed",
            has_analysis=final_state.get("analysis") is not None,
            errors=len(final_state.get("errors", [])),
        )

    except Exception as e:
        log.exception("investigation failed")


async def _process_custom_alert(
    payload: dict,
    investigation_id: str,
) -> None:
    """
    Process a custom alert in the background.

    Args:
        payload: Custom alert payload.
        investigation_id: Unique ID for this investigation.
    """
    log = logger.bind(
        handler="custom_alert_processor",
        investigation_id=investigation_id,
        service=payload.get("service_name"),
    )

    try:
        from sre_copilot.agent.state import AlertContext

        # Build alert context from custom payload
        severity_raw = payload.get("severity", "warning").lower()
        severity = "critical" if "crit" in severity_raw else (
            "warning" if "warn" in severity_raw else "info"
        )

        alert_context = AlertContext(
            alert_name=payload.get("alert_name", "CustomAlert"),
            severity=severity,
            service_name=payload["service_name"],
            cluster=payload.get("cluster", "unknown"),
            namespace=payload.get("namespace", "production"),
            pod=payload.get("pod"),
            timestamp=datetime.utcnow(),
            description=payload.get("description", ""),
            raw_payload=payload,
        )

        log.info(
            "starting custom investigation",
            service=alert_context.service_name,
            namespace=alert_context.namespace,
        )

        # Create initial state
        settings = get_settings()
        initial_state = AgentState(
            alert=alert_context,
            slack_channel=settings.slack_alert_channel if settings.slack_bot_token else None,
        )

        # Run investigation
        final_state = await run_investigation(initial_state)

        log.info(
            "custom investigation completed",
            has_analysis=final_state.get("analysis") is not None,
            errors=len(final_state.get("errors", [])),
        )

    except Exception as e:
        log.exception("custom investigation failed")


# Module-level app instance
_webhook_app: FastAPI | None = None


def get_webhook_app() -> FastAPI:
    """
    Get the webhook app instance (singleton).

    Returns:
        Configured FastAPI app.
    """
    global _webhook_app

    if _webhook_app is None:
        _webhook_app = create_webhook_app()

    return _webhook_app


async def start_webhook_server() -> None:
    """
    Start the webhook server.

    This runs indefinitely and handles incoming webhooks.
    """
    settings = get_settings()

    if not settings.enable_webhook:
        logger.info("webhook server disabled")
        return

    log = logger.bind(
        component="webhook_server",
        host=settings.webhook_host,
        port=settings.webhook_port,
    )
    log.info("starting webhook server")

    app = get_webhook_app()

    config = uvicorn.Config(
        app=app,
        host=settings.webhook_host,
        port=settings.webhook_port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()
