"""ISyncOutboxRepository — жергілікті sync outbox (durable кезек)
интерфейсі (Offline-First + Cloud Sync Foundation фазасы).

§ "Local Sync Queue" — қолданба қайта іске қосылса да сақталатын
кезек. §7 "Queue Deduplication": ``enqueue()`` идемпотентті —
``(entity_type, entity_sync_id)`` жұбына БҰРЫН күтілетін жазба бар
болса, ОНЫ АЛМАСТЫРАДЫ (жаңа operation/уақыт, retry есептегіштерін
ЫҚТИМАЛ түрде ысырады) — event sourcing ЖОҚ, "ЕҢ СОҢҒЫ ниет жеңеді".
"""

from abc import ABC, abstractmethod
from datetime import datetime

from domain.entities.outbox_entry import OutboxEntry, OutboxOperation


class ISyncOutboxRepository(ABC):
    @abstractmethod
    def enqueue(self, entity_type: str, entity_sync_id: str, operation: OutboxOperation) -> None:
        """Жаңа кезек жазбасын қосады немесе ЕСКІ КҮТІЛЕТІН жазбаны
        (§ дедупликация) АЛМАСТЫРАДЫ."""
        raise NotImplementedError

    @abstractmethod
    def list_due(self, now: datetime, limit: int = 100) -> tuple[OutboxEntry, ...]:
        """``next_retry_at`` ЖОҚ немесе ``<= now`` жазбаларды, ``created_at``
        бойынша сұрыпталған қайтарады (§ ретпен жіберу)."""
        raise NotImplementedError

    @abstractmethod
    def list_all(self) -> tuple[OutboxEntry, ...]:
        raise NotImplementedError

    @abstractmethod
    def count_pending(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def mark_success(self, entry_id: int) -> None:
        """Сәтті жіберілген жазбаны кезектен толығымен алып тастайды."""
        raise NotImplementedError

    @abstractmethod
    def mark_failure(self, entry_id: int, error: str, next_retry_at: datetime) -> None:
        """Сәтсіз әрекетті есептеп, келесі қайталау уақытын жазады —
        жазба кезекте ҚАЛАДЫ (§ "Temporary failure must not lose data")."""
        raise NotImplementedError
