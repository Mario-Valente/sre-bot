"""Prometheus HTTP client implementation."""

from datetime import datetime
from typing import Any

import httpx
import structlog

from sre_copilot.clients.protocols import MetricsClient, MetricsQueryError
from sre_copilot.config import get_settings

logger = structlog.get_logger()


class PrometheusClient(MetricsClient):
    """
    HTTP client for Prometheus API.

    Implements the MetricsClient protocol for querying Prometheus.

    API Documentation:
        https://prometheus.io/docs/prometheus/latest/querying/api/
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        headers: dict[str, str] | None = None,
    ):
        """
        Initialize Prometheus client.

        Args:
            base_url: Prometheus server URL. Defaults to settings.
            timeout: Request timeout in seconds. Defaults to settings.
            headers: Additional HTTP headers.
        """
        settings = get_settings()
        self.base_url = (base_url or settings.prometheus_url).rstrip("/")
        self.timeout = timeout or settings.query_timeout_seconds
        self.headers = headers or {}
        self._log = logger.bind(client="prometheus", base_url=self.base_url)

    async def query(self, query: str) -> list[dict[str, Any]]:
        """
        Execute an instant query.

        Endpoint: GET /api/v1/query

        Args:
            query: PromQL query string.

        Returns:
            Normalized list of metric series.

        Raises:
            MetricsQueryError: If the query fails.
        """
        self._log.debug("executing instant query", query=query)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/query",
                    params={"query": query},
                    headers=self.headers,
                )
                response.raise_for_status()
                data = response.json()

                if data.get("status") != "success":
                    error_msg = data.get("error", "Unknown error")
                    self._log.error("query failed", query=query, error=error_msg)
                    raise MetricsQueryError(f"Prometheus query failed: {error_msg}")

                result = self._parse_result(data["data"]["result"])
                self._log.debug(
                    "query completed", query=query, series_count=len(result)
                )
                return result

        except httpx.HTTPStatusError as e:
            self._log.error(
                "HTTP error", query=query, status=e.response.status_code
            )
            raise MetricsQueryError(
                f"Prometheus HTTP error: {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            self._log.error("request error", query=query, error=str(e))
            raise MetricsQueryError(f"Prometheus request error: {e}") from e

    async def query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = "15s",
    ) -> list[dict[str, Any]]:
        """
        Execute a range query.

        Endpoint: GET /api/v1/query_range

        Args:
            query: PromQL query string.
            start: Start of the time range.
            end: End of the time range.
            step: Query resolution step.

        Returns:
            Normalized list of metric series with time values.

        Raises:
            MetricsQueryError: If the query fails.
        """
        self._log.debug(
            "executing range query",
            query=query,
            start=start.isoformat(),
            end=end.isoformat(),
            step=step,
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/query_range",
                    params={
                        "query": query,
                        "start": start.timestamp(),
                        "end": end.timestamp(),
                        "step": step,
                    },
                    headers=self.headers,
                )
                response.raise_for_status()
                data = response.json()

                if data.get("status") != "success":
                    error_msg = data.get("error", "Unknown error")
                    self._log.error("range query failed", query=query, error=error_msg)
                    raise MetricsQueryError(f"Prometheus query failed: {error_msg}")

                result = self._parse_result(data["data"]["result"])
                self._log.debug(
                    "range query completed", query=query, series_count=len(result)
                )
                return result

        except httpx.HTTPStatusError as e:
            self._log.error(
                "HTTP error", query=query, status=e.response.status_code
            )
            raise MetricsQueryError(
                f"Prometheus HTTP error: {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            self._log.error("request error", query=query, error=str(e))
            raise MetricsQueryError(f"Prometheus request error: {e}") from e

    def _parse_result(self, result: list[dict]) -> list[dict[str, Any]]:
        """
        Convert Prometheus response to normalized format.

        Input (Prometheus format):
            [{"metric": {"__name__": "cpu", "pod": "x"}, "values": [[ts, val], ...]}]

        Output (normalized):
            [{"labels": {"name": "cpu", "pod": "x"}, "values": [{"timestamp": ..., "value": ...}]}]
        """
        normalized = []

        for series in result:
            labels = dict(series.get("metric", {}))

            # query_range returns "values", instant query returns "value"
            if "values" in series:
                values = [
                    {"timestamp": float(ts), "value": self._safe_float(val)}
                    for ts, val in series["values"]
                ]
            else:
                ts, val = series.get("value", [0, "0"])
                values = [{"timestamp": float(ts), "value": self._safe_float(val)}]

            normalized.append({"labels": labels, "values": values})

        return normalized

    @staticmethod
    def _safe_float(value: str | float) -> float:
        """
        Safely convert Prometheus value to float.

        Handles special values like "NaN", "+Inf", "-Inf".
        """
        if isinstance(value, float):
            return value
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0
