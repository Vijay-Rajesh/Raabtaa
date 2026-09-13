import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ArrivalAgentContext:
    """
    Runtime context passed to the Safe Arrival Agent and its tools.

    This carries only IDs and a DB session -- never raw secrets -- and is
    the sole channel through which tools reach the database / services.
    The agent itself never sees a DB session directly, only tool outputs.
    """

    db: AsyncSession
    user_id: uuid.UUID
    geofence_event_id: uuid.UUID
    safe_place_id: uuid.UUID
