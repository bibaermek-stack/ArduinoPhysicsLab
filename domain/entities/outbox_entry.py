"""OutboxEntry — жергілікті sync outbox кезегіндегі бір жазба
(Offline-First + Cloud Sync Foundation фазасы).

§ "Local Sync Queue" — қолданба қайта іске қосылса да сақталатын
durable кезек. Бір ``(entity_type, entity_sync_id)`` жұбына ЕҢ КӨП БІР
күтілетін жазба сәйкес келеді (§ "Queue Deduplication" — жаңа UPSERT
ескісін АЛМАСТЫРАДЫ, event sourcing ЖОҚ, § ``ISyncOutboxRepository.
enqueue()``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class OutboxOperation(Enum):
    UPSERT = "upsert"
    DELETE = "delete"


@dataclass(frozen=True)
class OutboxEntry:
    id: int
    entity_type: str
    entity_sync_id: str
    operation: OutboxOperation
    created_at: datetime
    attempt_count: int = 0
    last_error: str = ""
    next_retry_at: datetime | None = None
