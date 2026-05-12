"""Tempo HTTP client implementation."""

from datetime import datetime
from typing import Any

import httpx
import structlog

from sre_copilot.clients.protocols import TracesClient, TracesQueryError
from sre_copilot.config import get_settings

logger = structlog.get_logger()


class TempoClient(TracesClient):
    """
    HTTP client for Tempo API.

    Implements the TracesClient protocol for querying Tempo.

    API Documentation:
        https://grafana.com/docs/tempo/latest/api_docs/
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        headers: dict[str, str] | None = None,
    ):
        """
        Initialize Tempo client.

        Args:
            base_url: Tempo server URL. Defaults to settings.
            timeout: Request timeout in seconds. Defaults to settings.
            headers: Additional HTTP headers.
        """
        settings = get_settings()
        self.base_url = (base_url or settings.tempo_url).rstrip("/")
        self.timeout = timeout or settings.query_timeout_seconds
        self.headers = headers or {}
        self._log = logger.bind(client="tempo", base_url=self.base_url)

    async def search(
        self,
        service_name: str,
        start: datetime,
        end: datetime,
        min_duration: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Search for traces using TraceQL.

        Endpoint: GET /api/search

        Args:
            service_name: Name of the service to search.
            start: Start of the time range.
            end: End of the time range.
            min_duration: Minimum trace duration (e.g., "100ms").
            status: Filter by status ("error", "ok").
            limit: Maximum number of traces.

        Returns:
            List of trace summaries.

        Raises:
            TracesQueryError: If the search fails.
        """
        # Build TraceQL query
        query = self._build_traceql(service_name, min_duration, status)

        self._log.debug(
            "searching traces",
            query=query,
            start=start.isoformat(),
            end=end.isoformat(),
            limit=limit,
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/search",
                    params={
                        "q": query,
                        "start": int(start.timestamp()),
                        "end": int(end.timestamp()),
                        "limit": limit,
                    },
                    headers=self.headers,
                )
                response.raise_for_status()
                data = response.json()

                traces = self._parse_search_result(data.get("traces", []))
                self._log.debug("search completed", query=query, traces_count=len(traces))
                return traces

        except httpx.HTTPStatusError as e:
            self._log.error("HTTP error", query=query, status=e.response.status_code)
            raise TracesQueryError(f"Tempo HTTP error: {e.response.status_code}") from e
        except httpx.RequestError as e:
            self._log.error("request error", query=query, error=str(e))
            raise TracesQueryError(f"Tempo request error: {e}") from e

    async def get_trace(self, trace_id: str) -> dict[str, Any]:
        """
        Fetch a specific trace by ID.

        Endpoint: GET /api/traces/{traceID}

        Args:
            trace_id: The trace ID to fetch.

        Returns:
            Full trace data with all spans.

        Raises:
            TracesQueryError: If the trace cannot be fetched.
        """
        self._log.debug("fetching trace", trace_id=trace_id)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/traces/{trace_id}",
                    headers=self.headers,
                )
                response.raise_for_status()
                data = response.json()

                trace = self._parse_trace(data, trace_id)
                self._log.debug(
                    "trace fetched",
                    trace_id=trace_id,
                    spans_count=len(trace.get("spans", [])),
                )
                return trace

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self._log.warning("trace not found", trace_id=trace_id)
                raise TracesQueryError(f"Trace not found: {trace_id}") from e
            self._log.error("HTTP error", trace_id=trace_id, status=e.response.status_code)
            raise TracesQueryError(f"Tempo HTTP error: {e.response.status_code}") from e
        except httpx.RequestError as e:
            self._log.error("request error", trace_id=trace_id, error=str(e))
            raise TracesQueryError(f"Tempo request error: {e}") from e

    def _build_traceql(
        self,
        service_name: str,
        min_duration: str | None = None,
        status: str | None = None,
    ) -> str:
        """
        Build a TraceQL query string.

        Args:
            service_name: Service name to filter.
            min_duration: Minimum duration filter.
            status: Status filter.

        Returns:
            TraceQL query string.
        """
        conditions = [f'resource.service.name="{service_name}"']

        if min_duration:
            conditions.append(f"duration>{min_duration}")

        if status == "error":
            conditions.append("status=error")
        elif status == "ok":
            conditions.append("status=ok")

        return "{" + " && ".join(conditions) + "}"

    def _parse_search_result(self, traces: list[dict]) -> list[dict[str, Any]]:
        """
        Parse Tempo search results to normalized format.

        Args:
            traces: Raw traces from Tempo API.

        Returns:
            Normalized trace summaries.
        """
        normalized = []

        for trace in traces:
            normalized.append(
                {
                    "trace_id": trace.get("traceID", ""),
                    "root_service_name": trace.get("rootServiceName", ""),
                    "root_trace_name": trace.get("rootTraceName", ""),
                    "start_time": self._parse_timestamp(trace.get("startTimeUnixNano", 0)),
                    "duration_ms": trace.get("durationMs", 0),
                    "span_sets": trace.get("spanSets", []),
                }
            )

        return normalized

    def _parse_trace(self, data: dict, trace_id: str) -> dict[str, Any]:
        """
        Parse a full trace response.

        Args:
            data: Raw trace data from Tempo API.
            trace_id: The trace ID.

        Returns:
            Normalized trace with spans.
        """
        spans = []
        batches = data.get("batches", [])

        for batch in batches:
            resource = batch.get("resource", {})
            resource_attrs = self._extract_attributes(resource.get("attributes", []))
            service_name = resource_attrs.get("service.name", "unknown")

            scope_spans = batch.get("scopeSpans", [])
            for scope in scope_spans:
                for span in scope.get("spans", []):
                    spans.append(
                        {
                            "span_id": span.get("spanId", ""),
                            "trace_id": span.get("traceId", trace_id),
                            "parent_span_id": span.get("parentSpanId", ""),
                            "name": span.get("name", ""),
                            "service_name": service_name,
                            "start_time": self._parse_timestamp(span.get("startTimeUnixNano", 0)),
                            "end_time": self._parse_timestamp(span.get("endTimeUnixNano", 0)),
                            "duration_ms": self._calculate_duration(
                                span.get("startTimeUnixNano", 0),
                                span.get("endTimeUnixNano", 0),
                            ),
                            "status": self._parse_status(span.get("status", {})),
                            "attributes": self._extract_attributes(span.get("attributes", [])),
                        }
                    )

        return {
            "trace_id": trace_id,
            "spans": spans,
            "span_count": len(spans),
        }

    @staticmethod
    def _parse_timestamp(nano_ts: int | str) -> datetime:
        """Convert nanosecond timestamp to datetime."""
        if isinstance(nano_ts, str):
            nano_ts = int(nano_ts) if nano_ts else 0
        return datetime.fromtimestamp(nano_ts / 1_000_000_000)

    @staticmethod
    def _calculate_duration(start_ns: int | str, end_ns: int | str) -> float:
        """Calculate duration in milliseconds."""
        if isinstance(start_ns, str):
            start_ns = int(start_ns) if start_ns else 0
        if isinstance(end_ns, str):
            end_ns = int(end_ns) if end_ns else 0
        return (end_ns - start_ns) / 1_000_000

    @staticmethod
    def _parse_status(status: dict) -> str:
        """Parse span status to string."""
        code = status.get("code", 0)
        if code == 2:  # ERROR
            return "error"
        return "ok"

    @staticmethod
    def _extract_attributes(attributes: list[dict]) -> dict[str, str]:
        """Extract attributes from OTLP format."""
        result = {}
        for attr in attributes:
            key = attr.get("key", "")
            value = attr.get("value", {})
            # Handle different value types
            for value_type in ("stringValue", "intValue", "boolValue", "doubleValue"):
                if value_type in value:
                    result[key] = str(value[value_type])
                    break
        return result
