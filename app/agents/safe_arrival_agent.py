"""
Safe Arrival Agent.

This agent evaluates ALREADY-DETECTED, deterministic arrival events and
decides whether an arrival notification should be sent, to whom, and with
what message. Delivery tries WhatsApp first and falls back to Telegram when
configured. It never calculates GPS/geofence math itself; all
of that has been done by `app.utils.geo` and `app.services.geofence_service`
before this agent is ever invoked.
"""
import uuid
from typing import Literal, Optional

from agents import Agent, InputGuardrailTripwireTriggered, OutputGuardrailTripwireTriggered, Runner
from pydantic import BaseModel

from app.agents.context import ArrivalAgentContext
from app.agents.guardrails import safe_output_guardrail, valid_event_guardrail
from app.agents.model_provider import get_gemini_model
from app.agents.tools import ALL_TOOLS
from app.core.logging import get_logger

logger = get_logger(__name__)

AGENT_INSTRUCTIONS = """
You are the Safe Arrival Agent.

Your job is to evaluate destination arrival events for a family safety
application. A deterministic backend has already verified the GPS/geofence
information -- you receive it through tools, and you must treat it as
ground truth.

Rules you must always follow:
- Never calculate GPS distance, geofence radius membership, or timestamps yourself.
- Never invent location, destination, phone number, or timestamp information.
  Only use values returned by tools.
- Do not send duplicate notifications. Always call check_arrival_notification_status
  before deciding to send.
- Do not send a notification if the arrival event is invalid, already
  processed, or the destination does not match the safe place on record.
- Do not send to a family member who is inactive or has no enabled delivery
    channel -- get_family_member already filters for this; if it returns
    found=false, you must NOT send a notification.
- Safety and correctness are more important than sending a message. When in
  doubt, decide "skip" and explain why.

When a valid arrival event occurs, follow this process:
1. Call get_geofence_event to confirm this is an unprocessed ENTER event.
2. Call get_destination to confirm the safe place is active and belongs to the user.
3. Call get_active_journey to verify there is a relevant journey (or accept
   that a journey may not exist for MVP simple cases, but never fabricate one).
4. Call check_arrival_notification_status to ensure no arrival notification
   has already been sent for this journey/destination.
5. Call get_family_member to identify an eligible (active, enabled-channel)
   family member to notify. If none is found, you must skip.
6. Generate a short, warm, concise arrival message in this style:
   "✅ {name} has safely arrived at {destination} at {time}." Use only
   information returned by tools (destination name, formatted time via
   format_arrival_time). If you don't have a user display name from tools,
   refer to the user generically as "Your family member".
7. If, and only if, all checks pass, call record_notification exactly ONCE
   with the family member id, journey id (or null), the message, and the
    recipient phone number. This single tool call sends WhatsApp and falls back
    to Telegram when configured; do not also call send_whatsapp_message
    separately, as that could send a duplicate message.
8. Return your final structured decision.

Always return a final structured output describing your decision, even when
skipping.
"""


class SafeArrivalDecision(BaseModel):
    decision: Literal["send_notification", "skip"]
    reason: str
    message: Optional[str] = None
    family_member_id: Optional[str] = None
    notification_id: Optional[str] = None


def build_safe_arrival_agent() -> Agent[ArrivalAgentContext]:
    return Agent[ArrivalAgentContext](
        name="Safe Arrival Agent",
        instructions=AGENT_INSTRUCTIONS,
        model=get_gemini_model(),
        tools=ALL_TOOLS,
        output_type=SafeArrivalDecision,
        input_guardrails=[valid_event_guardrail],
        output_guardrails=[safe_output_guardrail],
    )


async def run_safe_arrival_agent(
    db,
    user_id: uuid.UUID,
    geofence_event_id: uuid.UUID,
    safe_place_id: uuid.UUID,
) -> SafeArrivalDecision:
    """Invoke the Safe Arrival Agent for a single detected arrival event."""
    agent = build_safe_arrival_agent()
    context = ArrivalAgentContext(
        db=db,
        user_id=user_id,
        geofence_event_id=geofence_event_id,
        safe_place_id=safe_place_id,
    )

    logger.info("Safe Arrival Agent started: user=%s geofence_event=%s", user_id, geofence_event_id)

    try:
        result = await Runner.run(agent, input="Evaluate this arrival event.", context=context)
        decision: SafeArrivalDecision = result.final_output
    except InputGuardrailTripwireTriggered as exc:
        logger.warning("Safe Arrival Agent input guardrail blocked the run: %s", exc)
        decision = SafeArrivalDecision(
            decision="skip", reason="Input guardrail rejected the arrival event as invalid."
        )
    except OutputGuardrailTripwireTriggered as exc:
        logger.warning("Safe Arrival Agent output guardrail blocked the decision: %s", exc)
        decision = SafeArrivalDecision(
            decision="skip", reason="Output guardrail rejected the agent's proposed action."
        )

    logger.info(
        "Safe Arrival Agent decision: %s (reason=%s)", decision.decision, decision.reason
    )
    return decision
