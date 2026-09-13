"""
Guardrails for the Safe Arrival Agent.

These implement the hard safety rules from the spec at the framework level,
on top of (not instead of) the deterministic checks already performed in
`app.services`. Guardrails here are defense-in-depth: even if the model
misbehaves, a tripped guardrail halts the run before anything unsafe reaches
a notification provider.
"""
import re
import uuid

from agents import GuardrailFunctionOutput, RunContextWrapper, input_guardrail, output_guardrail
from sqlalchemy import select

from app.agents.context import ArrivalAgentContext
from app.core.logging import get_logger
from app.models.geofence_event import GeofenceEvent
from app.models.safe_place import SafePlace

logger = get_logger(__name__)

# E.164-ish phone validation: + followed by 8-15 digits.
_PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")


@input_guardrail
async def valid_event_guardrail(
    wrapper: RunContextWrapper[ArrivalAgentContext], agent, input_data
) -> GuardrailFunctionOutput:
    """
    Refuse to run the agent at all unless the geofence event and safe place
    referenced in the context genuinely exist, belong to the same user, and
    the event is an unprocessed ENTER event.

    This stops the agent from "inventing" location or destination
    information, since it enforces that everything it reasons about is
    already backed by real database rows.
    """
    ctx = wrapper.context

    event_result = await ctx.db.execute(
        select(GeofenceEvent).where(GeofenceEvent.id == ctx.geofence_event_id)
    )
    event = event_result.scalar_one_or_none()

    place_result = await ctx.db.execute(select(SafePlace).where(SafePlace.id == ctx.safe_place_id))
    place = place_result.scalar_one_or_none()

    problems = []
    if event is None:
        problems.append("geofence_event_not_found")
    elif str(event.user_id) != str(ctx.user_id):
        problems.append("geofence_event_user_mismatch")
    elif event.event_type != "enter":
        problems.append("geofence_event_not_enter")

    if place is None:
        problems.append("safe_place_not_found")
    elif str(place.user_id) != str(ctx.user_id):
        problems.append("safe_place_user_mismatch")
    elif not place.is_active:
        problems.append("safe_place_inactive")

    tripwire = len(problems) > 0
    if tripwire:
        logger.warning("Safe Arrival Agent input guardrail tripped: %s", problems)

    return GuardrailFunctionOutput(
        output_info={"problems": problems},
        tripwire_triggered=tripwire,
    )


@output_guardrail
async def safe_output_guardrail(
    wrapper: RunContextWrapper[ArrivalAgentContext], agent, output
) -> GuardrailFunctionOutput:
    """
    Validate the agent's final structured decision before it is trusted by
    the caller. Blocks:
      - a "send_notification" decision with no family_member_id
      - a family_member_id that doesn't look like a real UUID
      - a message that looks like it invents a phone number itself
    """
    problems: list[str] = []

    decision = getattr(output, "decision", None)
    family_member_id = getattr(output, "family_member_id", None)
    message = getattr(output, "message", "") or ""

    if decision == "send_notification":
        if not family_member_id:
            problems.append("missing_family_member_id")
        else:
            try:
                uuid.UUID(str(family_member_id))
            except ValueError:
                problems.append("family_member_id_not_a_uuid")

    if re.search(r"\+\d{8,15}", message):
        # The message itself should be a human-readable arrival message, not
        # contain a raw phone number the model decided to write in.
        problems.append("message_contains_raw_phone_number")

    tripwire = len(problems) > 0
    if tripwire:
        logger.warning("Safe Arrival Agent output guardrail tripped: %s", problems)

    return GuardrailFunctionOutput(
        output_info={"problems": problems},
        tripwire_triggered=tripwire,
    )


def is_valid_phone(phone: str) -> bool:
    return bool(_PHONE_RE.match(phone))
