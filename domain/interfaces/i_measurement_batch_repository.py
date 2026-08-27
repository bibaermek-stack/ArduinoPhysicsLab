"""IMeasurementBatchRepository — raw Arduino measurement CHUNK/batch
sync orchestration (Phase 4: Raw Arduino Measurement Cloud Sync).

This repository does NOT own raw measurement storage (that remains
``ISessionRepository``/``measurements`` table, unchanged) — it owns
the PARENT metadata layer that groups a contiguous ``sequence_no``
range into one durable, independently-syncable unit (§ "the durable
synchronization unit should be a measurement batch/chunk", not
individual measurement rows — ``sync_outbox``'s ``UNIQUE(entity_type,
entity_sync_id)`` constraint could not otherwise support many
concurrent pending batches for the SAME session).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class IMeasurementBatchRepository(ABC):
    @abstractmethod
    def create_pending_batches_for_session(
        self, session_id: str, chunk_size: int, finalize: bool = False
    ) -> int:
        """Осы сессия үшін ӘЛІ batch-қа бөлінбеген ``measurements``
        ауқымын тексереді және толық ``chunk_size``-ті жаба алатын
        жаңа batch жол(дар)ын жасайды (§ "partial session upload" —
        тәжірибе жүріп жатқанда мерзімді шақырылуға арналған).
        ``finalize=True`` болса, ``chunk_size``-тен АЗ қалған "құйрық"
        өлшемдер де БІР соңғы (толық емес) batch-қа жиналады (§
        "Partially Filled Batches" — "do not lose tail samples").
        Жасалған batch санын қайтарады (§ идемпотентті — ЕШБІР қолда
        бар ауқым ҚАЙТА batch-қа бөлінбейді)."""
        raise NotImplementedError

    @abstractmethod
    def get_batch_sync_payload(self, batch_sync_id: str) -> dict | None:
        """Batch метадатасын + сол ауқымдағы НАҚТЫ measurement
        жолдарын (§ "raw data fidelity") сым (wire) payload түрінде
        қайтарады."""
        raise NotImplementedError

    @abstractmethod
    def apply_remote_batch(self, payload: dict) -> None:
        """§18 "Pull Sync": ЕШБІР outbox жазуы ЖАСАЛМАЙДЫ (§ established
        "apply_remote_* never re-enqueues" паттерні — әйтпесе pull->
        insert->outbox->push->pull шексіз циклі туар еді). Measurement
        жолдары ``INSERT OR IGNORE`` арқылы жазылады (§ ``UNIQUE(session_
        id, sequence_no)`` индексі — қайталама pull ЕШБІР дубликат
        жасамайды)."""
        raise NotImplementedError

    @abstractmethod
    def mark_batch_synced(self, batch_sync_id: str, server_revision: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def enqueue_batch_for_sync(self, batch_sync_id: str) -> None:
        """§ Legacy backfill: ескі (Phase 4 кодынан бұрын жазылған,
        batch-қа әлі бөлінбеген) сессияларды outbox-қа қосу үшін."""
        raise NotImplementedError

    @abstractmethod
    def list_pending_batch_ids_for_session(self, session_id: str) -> tuple[str, ...]:
        """Тестерге/диагностикаға арналған — осы сессияның batch_sync_id
        тізімін ``sequence_start`` бойынша сұрыпталған түрде қайтарады."""
        raise NotImplementedError
