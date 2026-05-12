"""Main entrypoint for the SRE Copilot agent."""

import asyncio
import logging
import signal
import sys
from typing import NoReturn

import structlog

from sre_copilot.config import get_settings

settings = get_settings()
log_level_name = settings.log_level.upper()
log_level = getattr(logging, log_level_name, logging.INFO)

logging.basicConfig(
    level=log_level,
    format="%(message)s",
)

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer()
        if sys.stderr.isatty()
        else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


async def run_services() -> None:
    """
    Run all enabled services concurrently.

    Starts the webhook server and/or Slack listener based on configuration.
    """
    settings = get_settings()
    log = logger.bind(component="main")

    tasks = []

    # Start webhook server if enabled
    if settings.enable_webhook:
        from sre_copilot.integrations.webhook import start_webhook_server

        log.info(
            "starting webhook server",
            host=settings.webhook_host,
            port=settings.webhook_port,
        )
        tasks.append(asyncio.create_task(start_webhook_server()))

    # Start Slack listener if enabled
    if settings.enable_slack_listener:
        if settings.slack_bot_token and settings.slack_app_token:
            from sre_copilot.integrations.slack import start_slack_listener

            log.info("starting Slack listener")
            tasks.append(asyncio.create_task(start_slack_listener()))
        else:
            log.warning(
                "Slack listener enabled but tokens not configured",
                has_bot_token=settings.slack_bot_token is not None,
                has_app_token=settings.slack_app_token is not None,
            )

    if not tasks:
        log.error("no services enabled - nothing to run")
        log.info("enable at least one: ENABLE_WEBHOOK=true or ENABLE_SLACK_LISTENER=true")
        return

    log.info("all services started", service_count=len(tasks))

    # Wait for all tasks
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        log.info("services cancelled")
        raise


def setup_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    """Set up signal handlers for graceful shutdown."""
    log = logger.bind(component="signals")

    def handle_signal(signum: int, frame) -> None:  # noqa: ARG001
        log.info("received shutdown signal", signal=signal.Signals(signum).name)
        for task in asyncio.all_tasks(loop):
            task.cancel()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)


def print_banner() -> None:
    """Print startup banner."""
    banner = """
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   ███████╗██████╗ ███████╗     ██████╗ ██████╗ ██████╗    ║
║   ██╔════╝██╔══██╗██╔════╝    ██╔════╝██╔═══██╗██╔══██╗   ║
║   ███████╗██████╔╝█████╗      ██║     ██║   ██║██████╔╝   ║
║   ╚════██║██╔══██╗██╔══╝      ██║     ██║   ██║██╔═══╝    ║
║   ███████║██║  ██║███████╗    ╚██████╗╚██████╔╝██║        ║
║   ╚══════╝╚═╝  ╚═╝╚══════╝     ╚═════╝ ╚═════╝ ╚═╝        ║
║                                                           ║
║            Autonomous Incident Triage Agent               ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
"""
    print(banner)


def print_config_summary() -> None:
    """Print configuration summary."""
    settings = get_settings()
    log = logger.bind(component="config")

    from sre_copilot.llm.factory import get_llm_info

    llm_info = get_llm_info()

    log.info(
        "configuration loaded",
        llm_provider=llm_info["provider"],
        llm_model=llm_info["model"],
        webhook_enabled=settings.enable_webhook,
        slack_enabled=settings.enable_slack_listener,
        prometheus_url=settings.prometheus_url,
        loki_url=settings.loki_url,
        tempo_url=settings.tempo_url,
    )


def main() -> NoReturn:
    """Main entrypoint."""
    print_banner()

    log = logger.bind(component="main")
    log.info("starting SRE Copilot")

    try:
        print_config_summary()
    except Exception as e:
        log.error("configuration error", error=str(e))
        sys.exit(1)

    # Create event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Set up signal handlers
    setup_signal_handlers(loop)

    try:
        loop.run_until_complete(run_services())
    except KeyboardInterrupt:
        log.info("interrupted by user")
    except asyncio.CancelledError:
        log.info("shutdown complete")
    except Exception:
        log.exception("fatal error")
        sys.exit(1)
    finally:
        loop.close()

    log.info("SRE Copilot stopped")
    sys.exit(0)


if __name__ == "__main__":
    main()
