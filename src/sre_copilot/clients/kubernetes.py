"""Kubernetes API client implementation."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any

import structlog
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

from sre_copilot.clients.protocols import KubernetesQueryError
from sre_copilot.config import get_settings

logger = structlog.get_logger()

# Thread pool for running sync K8s client in async context
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="k8s-")


class KubernetesClient:
    """
    Client for Kubernetes API.

    Provides methods for fetching pod information, logs, events,
    and deployment status for incident investigation.

    Note: The official kubernetes-client is synchronous, so we run
    it in a thread pool to avoid blocking the async event loop.
    """

    def __init__(
        self,
        in_cluster: bool | None = None,
        config_path: str | None = None,
        context: str | None = None,
    ):
        """
        Initialize Kubernetes client.

        Args:
            in_cluster: Use in-cluster config. Defaults to settings.
            config_path: Path to kubeconfig file. Defaults to settings.
            context: Kubernetes context to use. Defaults to settings.
        """
        settings = get_settings()
        self._in_cluster = in_cluster if in_cluster is not None else settings.kubernetes_in_cluster
        self._config_path = config_path or settings.kubernetes_config_path
        self._context = context or settings.kubernetes_context
        self._log = logger.bind(client="kubernetes")
        self._core_v1: client.CoreV1Api | None = None
        self._apps_v1: client.AppsV1Api | None = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Initialize the K8s client (must be called in thread pool)."""
        if self._initialized:
            return

        try:
            if self._in_cluster:
                config.load_incluster_config()
                self._log.debug("loaded in-cluster config")
            else:
                config.load_kube_config(
                    config_file=self._config_path,
                    context=self._context,
                )
                self._log.debug(
                    "loaded kubeconfig",
                    config_path=self._config_path,
                    context=self._context,
                )

            self._core_v1 = client.CoreV1Api()
            self._apps_v1 = client.AppsV1Api()
            self._initialized = True

        except Exception as e:
            self._log.error("failed to initialize kubernetes client", error=str(e))
            raise KubernetesQueryError(f"Failed to initialize K8s client: {e}") from e

    async def _run_sync(self, func, *args, **kwargs) -> Any:
        """Run a synchronous function in thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor,
            partial(func, *args, **kwargs),
        )

    async def get_pod(self, name: str, namespace: str) -> dict[str, Any]:
        """
        Get pod details (equivalent to kubectl describe pod).

        Args:
            name: Pod name (can be partial - will match first pod).
            namespace: Kubernetes namespace.

        Returns:
            Pod details including status, conditions, containers, events.

        Raises:
            KubernetesQueryError: If the query fails.
        """
        self._log.debug("fetching pod", name=name, namespace=namespace)

        def _get_pod():
            self._ensure_initialized()
            assert self._core_v1 is not None

            # If name is partial, list pods and find matching one
            pods = self._core_v1.list_namespaced_pod(
                namespace=namespace,
                label_selector=f"app={name}" if not name.endswith("-") else None,
            )

            # Try to find exact match first, then prefix match
            target_pod = None
            for pod in pods.items:
                if pod.metadata.name == name:
                    target_pod = pod
                    break
                if pod.metadata.name.startswith(name):
                    target_pod = pod
                    break

            # If no match by label, try direct get
            if target_pod is None:
                try:
                    target_pod = self._core_v1.read_namespaced_pod(name, namespace)
                except ApiException as e:
                    if e.status == 404:
                        return None
                    raise

            if target_pod is None:
                return None

            return self._parse_pod(target_pod)

        try:
            return await self._run_sync(_get_pod)
        except ApiException as e:
            self._log.error("API error fetching pod", name=name, error=str(e))
            raise KubernetesQueryError(f"Failed to get pod {name}: {e}") from e

    async def get_pods_for_service(self, service_name: str, namespace: str) -> list[dict[str, Any]]:
        """
        Get all pods for a service.

        Args:
            service_name: Service/app name to match.
            namespace: Kubernetes namespace.

        Returns:
            List of pod details.

        Raises:
            KubernetesQueryError: If the query fails.
        """
        self._log.debug("fetching pods for service", service=service_name, namespace=namespace)

        def _get_pods():
            self._ensure_initialized()
            assert self._core_v1 is not None

            # Try common label selectors
            selectors = [
                f"app={service_name}",
                f"app.kubernetes.io/name={service_name}",
            ]

            all_pods = []
            for selector in selectors:
                try:
                    pods = self._core_v1.list_namespaced_pod(
                        namespace=namespace,
                        label_selector=selector,
                    )
                    all_pods.extend(pods.items)
                except ApiException:
                    continue

            # Remove duplicates by pod name
            seen = set()
            unique_pods = []
            for pod in all_pods:
                if pod.metadata.name not in seen:
                    seen.add(pod.metadata.name)
                    unique_pods.append(pod)

            return [self._parse_pod(pod) for pod in unique_pods]

        try:
            return await self._run_sync(_get_pods)
        except ApiException as e:
            self._log.error("API error fetching pods", service=service_name, error=str(e))
            raise KubernetesQueryError(f"Failed to get pods for {service_name}: {e}") from e

    async def get_pod_logs(
        self,
        name: str,
        namespace: str,
        container: str | None = None,
        tail_lines: int | None = None,
        previous: bool = False,
    ) -> str:
        """
        Get pod logs.

        Args:
            name: Pod name.
            namespace: Kubernetes namespace.
            container: Container name (optional, defaults to first).
            tail_lines: Number of lines to fetch. Defaults to settings.
            previous: Get logs from previous container instance.

        Returns:
            Log content as string.

        Raises:
            KubernetesQueryError: If the query fails.
        """
        settings = get_settings()
        lines = tail_lines or settings.kubernetes_log_lines

        self._log.debug(
            "fetching pod logs",
            name=name,
            namespace=namespace,
            container=container,
            tail_lines=lines,
        )

        def _get_logs():
            self._ensure_initialized()
            assert self._core_v1 is not None

            return self._core_v1.read_namespaced_pod_log(
                name=name,
                namespace=namespace,
                container=container,
                tail_lines=lines,
                previous=previous,
            )

        try:
            return await self._run_sync(_get_logs)
        except ApiException as e:
            self._log.error("API error fetching logs", name=name, error=str(e))
            raise KubernetesQueryError(f"Failed to get logs for {name}: {e}") from e

    async def get_events(
        self,
        namespace: str,
        involved_object_name: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Get Kubernetes events.

        Args:
            namespace: Kubernetes namespace.
            involved_object_name: Filter by involved object name.
            limit: Maximum number of events.

        Returns:
            List of events with type, reason, message, etc.

        Raises:
            KubernetesQueryError: If the query fails.
        """
        self._log.debug(
            "fetching events",
            namespace=namespace,
            object=involved_object_name,
        )

        def _get_events():
            self._ensure_initialized()
            assert self._core_v1 is not None

            field_selector = None
            if involved_object_name:
                field_selector = f"involvedObject.name={involved_object_name}"

            events = self._core_v1.list_namespaced_event(
                namespace=namespace,
                field_selector=field_selector,
                limit=limit,
            )

            parsed = []
            for event in events.items:
                parsed.append(
                    {
                        "type": event.type,
                        "reason": event.reason,
                        "message": event.message,
                        "count": event.count or 1,
                        "first_timestamp": event.first_timestamp.isoformat()
                        if event.first_timestamp
                        else None,
                        "last_timestamp": event.last_timestamp.isoformat()
                        if event.last_timestamp
                        else None,
                        "involved_object": {
                            "kind": event.involved_object.kind,
                            "name": event.involved_object.name,
                        },
                        "source": event.source.component if event.source else None,
                    }
                )

            # Sort by last_timestamp descending
            parsed.sort(
                key=lambda e: e.get("last_timestamp") or "",
                reverse=True,
            )

            return parsed

        try:
            return await self._run_sync(_get_events)
        except ApiException as e:
            self._log.error("API error fetching events", namespace=namespace, error=str(e))
            raise KubernetesQueryError(f"Failed to get events: {e}") from e

    async def get_deployment(self, name: str, namespace: str) -> dict[str, Any] | None:
        """
        Get deployment details.

        Args:
            name: Deployment name.
            namespace: Kubernetes namespace.

        Returns:
            Deployment details or None if not found.

        Raises:
            KubernetesQueryError: If the query fails.
        """
        self._log.debug("fetching deployment", name=name, namespace=namespace)

        def _get_deployment():
            self._ensure_initialized()
            assert self._apps_v1 is not None

            try:
                deployment = self._apps_v1.read_namespaced_deployment(name, namespace)
            except ApiException as e:
                if e.status == 404:
                    return None
                raise

            return {
                "name": deployment.metadata.name,
                "namespace": deployment.metadata.namespace,
                "replicas": {
                    "desired": deployment.spec.replicas,
                    "ready": deployment.status.ready_replicas or 0,
                    "available": deployment.status.available_replicas or 0,
                    "unavailable": deployment.status.unavailable_replicas or 0,
                },
                "strategy": deployment.spec.strategy.type,
                "conditions": [
                    {
                        "type": c.type,
                        "status": c.status,
                        "reason": c.reason,
                        "message": c.message,
                        "last_update": c.last_update_time.isoformat()
                        if c.last_update_time
                        else None,
                    }
                    for c in (deployment.status.conditions or [])
                ],
                "created_at": deployment.metadata.creation_timestamp.isoformat(),
                "labels": dict(deployment.metadata.labels or {}),
            }

        try:
            return await self._run_sync(_get_deployment)
        except ApiException as e:
            self._log.error("API error fetching deployment", name=name, error=str(e))
            raise KubernetesQueryError(f"Failed to get deployment {name}: {e}") from e

    def _parse_pod(self, pod) -> dict[str, Any]:
        """Parse a V1Pod into a simplified dict."""
        containers = []
        for container in pod.spec.containers:
            container_status = None
            if pod.status.container_statuses:
                for cs in pod.status.container_statuses:
                    if cs.name == container.name:
                        container_status = cs
                        break

            state = "unknown"
            state_detail = {}
            if container_status and container_status.state:
                if container_status.state.running:
                    state = "running"
                    state_detail = {
                        "started_at": container_status.state.running.started_at.isoformat()
                        if container_status.state.running.started_at
                        else None
                    }
                elif container_status.state.waiting:
                    state = "waiting"
                    state_detail = {
                        "reason": container_status.state.waiting.reason,
                        "message": container_status.state.waiting.message,
                    }
                elif container_status.state.terminated:
                    state = "terminated"
                    state_detail = {
                        "reason": container_status.state.terminated.reason,
                        "exit_code": container_status.state.terminated.exit_code,
                        "message": container_status.state.terminated.message,
                    }

            containers.append(
                {
                    "name": container.name,
                    "image": container.image,
                    "state": state,
                    "state_detail": state_detail,
                    "ready": container_status.ready if container_status else False,
                    "restart_count": container_status.restart_count if container_status else 0,
                    "resources": {
                        "limits": dict(container.resources.limits)
                        if container.resources and container.resources.limits
                        else {},
                        "requests": dict(container.resources.requests)
                        if container.resources and container.resources.requests
                        else {},
                    },
                }
            )

        conditions = []
        if pod.status.conditions:
            for c in pod.status.conditions:
                conditions.append(
                    {
                        "type": c.type,
                        "status": c.status,
                        "reason": c.reason,
                        "message": c.message,
                        "last_transition": c.last_transition_time.isoformat()
                        if c.last_transition_time
                        else None,
                    }
                )

        return {
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "phase": pod.status.phase,
            "node": pod.spec.node_name,
            "ip": pod.status.pod_ip,
            "host_ip": pod.status.host_ip,
            "created_at": pod.metadata.creation_timestamp.isoformat()
            if pod.metadata.creation_timestamp
            else None,
            "labels": dict(pod.metadata.labels or {}),
            "containers": containers,
            "conditions": conditions,
            "restart_count": sum(c.get("restart_count", 0) for c in containers),
        }
