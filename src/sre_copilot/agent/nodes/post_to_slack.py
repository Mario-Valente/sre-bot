"""Node for posting analysis results to Slack."""

import structlog

from sre_copilot.agent.state import AgentState, IncidentAnalysis, StateUpdate

logger = structlog.get_logger()


async def post_to_slack(state: AgentState) -> StateUpdate:
    """
    Post the incident analysis to Slack.

    Formats the analysis as a Slack message and posts it
    as a reply in the original alert thread.

    Args:
        state: Current agent state with analysis.

    Returns:
        Updated state with Slack message metadata.
    """
    log = logger.bind(
        node="post_to_slack",
        service=state.alert.service_name,
        channel=state.slack_channel,
        thread_ts=state.slack_thread_ts,
    )

    if not state.analysis:
        log.warning("no analysis to post")
        return {"errors": ["No analysis available to post"]}

    if not state.slack_channel:
        log.info("no slack channel configured, skipping post")
        return {}

    log.info("posting analysis to Slack")

    try:
        # Import here to avoid circular imports and allow mocking
        from slack_sdk.web.async_client import AsyncWebClient

        from sre_copilot.config import get_settings

        settings = get_settings()

        if not settings.slack_bot_token:
            log.warning("Slack bot token not configured")
            return {"errors": ["Slack bot token not configured"]}

        token = settings.slack_bot_token.get_secret_value()
        if not token.startswith("xoxb-"):
            log.warning("invalid Slack bot token type", token_prefix=token[:16])
            return {
                "errors": [
                    "Slack bot token inválido: esperado token xoxb com escopo chat:write:bot"
                ]
            }

        client = AsyncWebClient(token=token)

        # Format message
        blocks = _format_analysis_blocks(state.alert, state.analysis)
        text = _format_analysis_text(state.alert, state.analysis)

        # Post message
        response = await client.chat_postMessage(
            channel=state.slack_channel,
            thread_ts=state.slack_thread_ts,  # Reply in thread
            text=text,  # Fallback text
            blocks=blocks,
            unfurl_links=False,
            unfurl_media=False,
        )

        message_ts = response.get("ts")
        log.info("analysis posted to Slack", message_ts=message_ts)

        return {"slack_message_ts": message_ts}

    except Exception as e:
        log.exception("failed to post to Slack")
        return {"errors": [f"Slack post failed: {str(e)}"]}


def _format_analysis_blocks(alert, analysis: IncidentAnalysis) -> list[dict]:
    """
    Format analysis as Slack blocks.

    Uses Block Kit for rich formatting.
    """
    # Determine emoji based on confidence and escalation
    if analysis.needs_human_escalation:
        emoji = ":rotating_light:"
        color = "danger"
    elif analysis.confidence == "high":
        emoji = ":white_check_mark:"
        color = "good"
    elif analysis.confidence == "medium":
        emoji = ":warning:"
        color = "warning"
    else:
        emoji = ":question:"
        color = "#808080"

    blocks = [
        # Header
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} Incident Analysis: {alert.service_name}",
                "emoji": True,
            },
        },
        # Summary
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Summary:* {analysis.summary}",
            },
        },
        {"type": "divider"},
        # Root Cause
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Probable Root Cause:*\n{analysis.probable_root_cause}",
            },
        },
    ]

    # Contributing factors
    if analysis.contributing_factors:
        factors_text = "\n".join(f"• {f}" for f in analysis.contributing_factors)
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Contributing Factors:*\n{factors_text}",
                },
            }
        )

    # Evidence
    if analysis.evidence:
        evidence_text = "\n".join(f"• {e}" for e in analysis.evidence[:5])
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Evidence:*\n{evidence_text}",
                },
            }
        )

    blocks.append({"type": "divider"})

    # Suggested Actions
    if analysis.suggested_actions:
        actions_text = "\n".join(f"{i + 1}. {a}" for i, a in enumerate(analysis.suggested_actions))
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Suggested Actions:*\n{actions_text}",
                },
            }
        )

    # Confidence and metadata
    confidence_emoji = {
        "high": ":green_circle:",
        "medium": ":yellow_circle:",
        "low": ":red_circle:",
    }.get(analysis.confidence, ":white_circle:")

    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"{confidence_emoji} *Confidence:* {analysis.confidence.upper()}",
                },
                {
                    "type": "mrkdwn",
                    "text": f":robot_face: _Automated analysis by SRE Copilot_",
                },
            ],
        }
    )

    # Escalation warning
    if analysis.needs_human_escalation:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f":rotating_light: *Human Escalation Required*\n"
                        f"Reason: {analysis.escalation_reason or 'See analysis for details'}"
                    ),
                },
            }
        )

    return blocks


def _format_analysis_text(alert, analysis: IncidentAnalysis) -> str:
    """
    Format analysis as plain text (fallback).

    Used when blocks cannot be rendered.
    """
    lines = [
        f"*Incident Analysis: {alert.service_name}*",
        "",
        f"*Summary:* {analysis.summary}",
        "",
        f"*Probable Root Cause:* {analysis.probable_root_cause}",
    ]

    if analysis.contributing_factors:
        lines.append("")
        lines.append("*Contributing Factors:*")
        for factor in analysis.contributing_factors:
            lines.append(f"• {factor}")

    if analysis.suggested_actions:
        lines.append("")
        lines.append("*Suggested Actions:*")
        for i, action in enumerate(analysis.suggested_actions, 1):
            lines.append(f"{i}. {action}")

    lines.append("")
    lines.append(f"*Confidence:* {analysis.confidence.upper()}")

    if analysis.needs_human_escalation:
        lines.append("")
        lines.append(f":rotating_light: *Human Escalation Required* - {analysis.escalation_reason}")

    return "\n".join(lines)
