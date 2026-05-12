"""Loki HTTP client implementation."""

from datetime import datetime
from typing import Any

import httpx
import structlog

from sre_copilot.clients.protocols import LogsClient, LogsQueryError
from sre_copilot.config import get_settings

logger = structlog.get_logger()


class LokiClient(LogsClient):
    """
    HTTP client for Loki API.

    Implements the LogsClient protocol for querying Loki.

    API Documentation:
        https://grafana.com/docs/loki/latest/reference/api/
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        headers: dict[str, str] | None = None,
    ):
        """
        Initialize Loki client.

        Args:
            base_url: Loki server URL. Defaults to settings.
            timeout: Request timeout in seconds. Defaults to settings.
            headers: Additional HTTP headers.
        """
        settings = get_settings()
        self.base_url = (base_url or settings.loki_url).rstrip("/")
        self.timeout = timeout or settings.query_timeout_seconds
        self.headers = headers or {}
        self._log = logger.bind(client="loki", base_url=self.base_url)

    async def query(
        self,
        query: str,
        start: datetime,
        end: datetime,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """
        Execute a LogQL query.

        Endpoint: GET /loki/api/v1/query_range

        Args:
            query: LogQL query string.
            start: Start of the time range.
            end: End of the time range.
            limit: Maximum number of log entries.

        Returns:
            List of log entries with timestamps and labels.

        Raises:
            LogsQueryError: If the query fails.
        """
        self._log.debug(
            "executing log query",
            query=query,
            start=start.isoformat(),
            end=end.isoformat(),
            limit=limit,
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/loki/api/v1/query_range",
                    params={
                        "query": query,
                        "start": self._to_nanoseconds(start),
                        "end": self._to_nanoseconds(end),
                        "limit": limit,
                    },
                    headers=self.headers,
                )
                response.raise_for_status()
                data = response.json()

                if data.get("status") != "success":
                    error_msg = data.get("error", "Unknown error")
                    self._log.error("query failed", query=query, error=error_msg)
                    raise LogsQueryError(f"Loki query failed: {error_msg}")

                result = self._parse_result(data["data"]["result"])
                self._log.debug("query completed", query=query, entries_count=len(result))
                return result

        except httpx.HTTPStatusError as e:
            self._log.error("HTTP error", query=query, status=e.response.status_code)
            raise LogsQueryError(f"Loki HTTP error: {e.response.status_code}") from e
        except httpx.RequestError as e:
            self._log.error("request error", query=query, error=str(e))
            raise LogsQueryError(f"Loki request error: {e}") from e

    def _parse_result(self, result: list[dict]) -> list[dict[str, Any]]:
        """
        Convert Loki response to normalized format.

        Input (Loki format):
            [{"stream": {"app": "x"}, "values": [["timestamp_ns", "log line"], ...]}]

        Output (normalized):
            [{"timestamp": datetime, "message": "log line", "labels": {...}}]
        """
        entries = []

        for stream in result:
            labels = dict(stream.get("stream", {}))

            for value in stream.get("values", []):
                if len(value) >= 2:
                    timestamp_ns, message = value[0], value[1]
                    entries.append(
                        {
                            "timestamp": self._from_nanoseconds(int(timestamp_ns)),
                            "message": message,
                            "labels": labels,
                            "level": self._extract_level(message, labels),
                        }
                    )

        # Sort by timestamp descending (most recent first)
        entries.sort(key=lambda x: x["timestamp"], reverse=True)
        return entries

    @staticmethod
    def _to_nanoseconds(dt: datetime) -> int:
        """Convert datetime to nanoseconds since epoch."""
        return int(dt.timestamp() * 1_000_000_000)

    @staticmethod
    def _from_nanoseconds(ns: int) -> datetime:
        """Convert nanoseconds since epoch to datetime."""
        return datetime.fromtimestamp(ns / 1_000_000_000)

    @staticmethod
    def _extract_level(message: str, labels: dict[str, str]) -> str:
        """
        Extract log level from message or labels.

        Checks labels first, then tries to parse from message.
        """
        # Check common label names
        for label_name in ("level", "severity", "log_level"):
            if label_name in labels:
                return labels[label_name].lower()

        # Try to extract from message
        message_lower = message.lower()
        for level in ("fatal", "error", "warn", "info", "debug", "trace"):
            if level in message_lower[:50]:  # Check only start of message
                return level

        return "unknown"
