"""Node for synthesizing analysis using LLM."""

from datetime import datetime

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from sre_copilot.agent.state import AgentState, IncidentAnalysis, StateUpdate
from sre_copilot.llm import get_llm

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are an expert SRE (Site Reliability Engineer) analyzing an incident.
Your task is to synthesize data from multiple sources and provide a root cause analysis.

Be concise, technical, and actionable. Focus on:
1. What happened (summary)
2. Why it happened (root cause hypothesis)
3. What evidence supports this
4. What to do next (mitigation steps)

Guidelines:
- Be specific with service names, error messages, and metrics
- Prioritize the most likely root cause based on evidence
- Suggest immediate actions, not long-term improvements
- If data is insufficient, say so and suggest what data to gather
- Set confidence based on evidence strength (high/medium/low)
- Flag for escalation if: data loss risk, security concern, or widespread impact

Output format: JSON matching the IncidentAnalysis schema."""


def _build_analysis_prompt(state: AgentState) -> str:
    """Build the analysis prompt with all collected data."""
    alert = state.alert
    sections = []

    # Alert context
    sections.append(f"""## Alert Context
- **Alert Name:** {alert.alert_name}
- **Severity:** {alert.severity}
- **Service:** {alert.service_name}
- **Namespace:** {alert.namespace}
- **Cluster:** {alert.cluster}
- **Timestamp:** {alert.timestamp.isoformat()}
- **Description:** {alert.description or "N/A"}
""")

    # Metrics
    if state.metrics:
        metrics = state.metrics
        metrics_section = "## Metrics (Prometheus)\n"

        if metrics.anomalies_detected:
            metrics_section += "**Anomalies Detected:**\n"
            for anomaly in metrics.anomalies_detected:
                metrics_section += f"- {anomaly}\n"

        if metrics.error_rate_5xx:
            metrics_section += "\n**Error Rate (5xx):** Data available\n"
        if metrics.latency_p99:
            metrics_section += "**P99 Latency:** Data available\n"
        if metrics.cpu_usage:
            metrics_section += "**CPU Usage:** Data available\n"
        if metrics.memory_usage:
            metrics_section += "**Memory Usage:** Data available\n"

        if metrics.query_errors:
            metrics_section += "\n**Query Errors:**\n"
            for err in metrics.query_errors:
                metrics_section += f"- {err}\n"

        sections.append(metrics_section)
    else:
        sections.append("## Metrics\nNo metrics data available.\n")

    # Logs
    if state.logs:
        logs = state.logs
        logs_section = f"## Logs (Loki)\n**Total Error/Fatal Logs:** {logs.total_error_count}\n"

        if logs.log_patterns:
            logs_section += "\n**Common Patterns:**\n"
            for pattern in logs.log_patterns[:5]:
                logs_section += f"- {pattern}\n"

        if logs.fatal_logs:
            logs_section += f"\n**Sample Fatal Logs ({len(logs.fatal_logs)}):**\n"
            for log_entry in logs.fatal_logs[:3]:
                logs_section += (
                    f"- [{log_entry.timestamp.strftime('%H:%M:%S')}] {log_entry.message[:200]}\n"
                )

        if logs.error_logs:
            logs_section += f"\n**Sample Error Logs ({len(logs.error_logs)}):**\n"
            for log_entry in logs.error_logs[:5]:
                logs_section += (
                    f"- [{log_entry.timestamp.strftime('%H:%M:%S')}] {log_entry.message[:200]}\n"
                )

        sections.append(logs_section)
    else:
        sections.append("## Logs\nNo log data available.\n")

    # Traces
    if state.traces:
        traces = state.traces
        traces_section = "## Traces (Tempo)\n"

        if traces.bottleneck_services:
            traces_section += "**Bottleneck Services:**\n"
            for svc in traces.bottleneck_services:
                traces_section += f"- {svc}\n"

        if traces.failed_traces:
            traces_section += f"\n**Failed Traces ({len(traces.failed_traces)}):**\n"
            for trace in traces.failed_traces[:3]:
                traces_section += (
                    f"- {trace.operation_name}: {trace.duration_ms:.0f}ms ({trace.service_name})\n"
                )

        if traces.slow_traces:
            traces_section += f"\n**Slow Traces ({len(traces.slow_traces)}):**\n"
            for trace in traces.slow_traces[:3]:
                traces_section += (
                    f"- {trace.operation_name}: {trace.duration_ms:.0f}ms ({trace.service_name})\n"
                )

        sections.append(traces_section)
    else:
        sections.append("## Traces\nNo trace data available.\n")

    # GitHub
    if state.github:
        github = state.github
        github_section = f"## Recent Changes (GitHub)\n**Repository:** {github.repository}\n"
        github_section += (
            f"**Recent Deploy Detected:** {'Yes' if github.has_recent_deploy else 'No'}\n"
        )

        if github.recent_commits:
            github_section += f"\n**Recent Commits ({len(github.recent_commits)}):**\n"
            for commit in github.recent_commits[:3]:
                github_section += f"- [{commit.sha}] {commit.message[:60]} ({commit.author})\n"

        if github.recent_prs:
            github_section += f"\n**Recent PRs ({len(github.recent_prs)}):**\n"
            for pr in github.recent_prs[:3]:
                github_section += f"- #{pr.number}: {pr.title[:50]} ({pr.author})\n"

        if github.last_release:
            release = github.last_release
            github_section += f"\n**Latest Release:** {release.tag} ({release.published_at.strftime('%Y-%m-%d')})\n"

        sections.append(github_section)
    else:
        sections.append("## Recent Changes\nNo GitHub data available.\n")

    # Execution errors
    if state.errors:
        sections.append("## Data Collection Errors\n" + "\n".join(f"- {e}" for e in state.errors))

    return "\n".join(sections)


async def synthesize(state: AgentState) -> StateUpdate:
    """
    Synthesize all collected data into a root cause analysis using LLM.

    Args:
        state: Current agent state with all collected data.

    Returns:
        Updated state with incident analysis.
    """
    log = logger.bind(
        node="synthesize",
        service=state.alert.service_name,
    )
    log.info("synthesizing incident analysis")

    try:
        llm = get_llm()

        # Build prompt
        analysis_prompt = _build_analysis_prompt(state)

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=f"""Analyze this incident and provide a root cause analysis.

{analysis_prompt}

Respond with a JSON object containing:
- summary: Brief 1-2 sentence summary
- probable_root_cause: Primary hypothesis
- contributing_factors: List of secondary factors
- evidence: List of data points supporting the hypothesis
- suggested_actions: List of immediate next steps
- confidence: "high", "medium", or "low"
- needs_human_escalation: true/false
- escalation_reason: Reason if escalation needed (optional)
"""
            ),
        ]

        # Invoke LLM
        response = await llm.ainvoke(messages)
        response_text = response.content

        # Parse response
        analysis = _parse_llm_response(response_text, log)

        log.info(
            "analysis completed",
            confidence=analysis.confidence,
            needs_escalation=analysis.needs_human_escalation,
        )

        return {
            "analysis": analysis,
            "completed_at": datetime.utcnow(),
        }

    except Exception as e:
        log.exception("failed to synthesize analysis")

        # Return a fallback analysis
        fallback = IncidentAnalysis(
            summary=f"Analysis failed for {state.alert.service_name} incident",
            probable_root_cause="Unable to determine - analysis failed",
            contributing_factors=[],
            evidence=[],
            suggested_actions=[
                "Manually review metrics in Grafana",
                "Check application logs in Loki",
                "Review recent deployments",
            ],
            confidence="low",
            needs_human_escalation=True,
            escalation_reason=f"Automated analysis failed: {str(e)}",
        )

        return {
            "analysis": fallback,
            "errors": [f"LLM synthesis failed: {str(e)}"],
            "completed_at": datetime.utcnow(),
        }


def _parse_llm_response(response_text: str, log) -> IncidentAnalysis:
    """Parse LLM response into IncidentAnalysis object."""
    import json
    import re

    # Try to extract JSON from response
    json_match = re.search(r"\{[\s\S]*\}", response_text)
    if json_match:
        try:
            data = json.loads(json_match.group())
            return IncidentAnalysis(
                summary=data.get("summary", "No summary provided"),
                probable_root_cause=data.get("probable_root_cause", "Unknown"),
                contributing_factors=data.get("contributing_factors", []),
                evidence=data.get("evidence", []),
                suggested_actions=data.get("suggested_actions", []),
                confidence=data.get("confidence", "low"),
                needs_human_escalation=data.get("needs_human_escalation", False),
                escalation_reason=data.get("escalation_reason"),
            )
        except json.JSONDecodeError as e:
            log.warning("failed to parse JSON response", error=str(e))

    # Fallback: create analysis from plain text
    log.warning("using fallback text parsing")
    return IncidentAnalysis(
        summary=response_text[:200] if response_text else "No analysis generated",
        probable_root_cause="See summary for details",
        contributing_factors=[],
        evidence=[],
        suggested_actions=["Review the analysis manually"],
        confidence="low",
        needs_human_escalation=True,
        escalation_reason="Could not parse structured analysis",
    )
