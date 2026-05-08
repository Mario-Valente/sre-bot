"""Graph nodes for the SRE Copilot agent."""

from sre_copilot.agent.nodes.extract_context import extract_context
from sre_copilot.agent.nodes.fetch_metrics import fetch_metrics
from sre_copilot.agent.nodes.fetch_logs import fetch_logs
from sre_copilot.agent.nodes.fetch_traces import fetch_traces
from sre_copilot.agent.nodes.fetch_kubernetes import fetch_kubernetes
from sre_copilot.agent.nodes.fetch_github import fetch_github
from sre_copilot.agent.nodes.synthesize import synthesize
from sre_copilot.agent.nodes.post_to_slack import post_to_slack

__all__ = [
    "extract_context",
    "fetch_metrics",
    "fetch_logs",
    "fetch_traces",
    "fetch_kubernetes",
    "fetch_github",
    "synthesize",
    "post_to_slack",
]
