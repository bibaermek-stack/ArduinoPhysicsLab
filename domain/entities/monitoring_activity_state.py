"""MonitoringActivityState — Phase 6 (Teacher Live Classroom Monitoring)
мұғалімге көрсетілетін "белсенділік" күйі.

§6 "Activity / Presence Semantics" — Phase 5 polling негізінде жұмыс
істейді (WebSocket/persistent presence ЖОҚ), сондықтан бұл ЕШҚАШАН
шынайы желілік "online/offline" емес — тек "соңғы синхрондалған дерек
қаншалықты жаңа" деген ХАЛАЛ (honest) қорытынды. ``domain/services/
teacher_monitoring.py::classify_activity()`` осы enum-ды НАҚТЫ
жазбалардан (progress статусы + соңғы measurement уақыты) есептейді —
ешбір UI компоненті бұл күйді өзі ойдан шығармайды.
"""

from __future__ import annotations

from enum import Enum


class MonitoringActivityState(Enum):
    # § Сессия байланысы мүлде жоқ (§ ``ProgressStatus.NOT_STARTED``).
    NOT_STARTED = "not_started"
    # § Сессия ``IN_PROGRESS`` ЖӘНЕ соңғы measurement ``active_window``
    # ішінде келген — Phase 5-тің ~10с белсенді-тәжірибе sync циклімен
    # сәйкес келетін "жаңа дерек" дәлелі.
    ACTIVE = "active"
    # § Сессия ``IN_PROGRESS``, БІРАҚ соңғы measurement ``active_window``-
    # дан АСЫП, ``stale_window``-ға ДЕЙІН — "дерек күтілуде" (қысқа
    # синхрондау кідірісі НЕМЕСЕ жақында желі үзілді, әлі белгісіз).
    STALE = "stale"
    # § Сессия ``IN_PROGRESS``, БІРАҚ соңғы measurement ``stale_window``-
    # дан АСЫП кетті — ұзақ уақыт ЕШБІР жаңа дерек жоқ (§ "honest, NOT a
    # proven network disconnect" — тек "ұзақ уақыт дәлел жоқ" мағынасы).
    OFFLINE = "offline"
    # § Сессия ``IN_PROGRESS``-тен КЕЙІНГІ кез-келген қорытынды статус
    # (``MEASUREMENT_COMPLETED``/``REPORT_COMPLETED``/``FEEDBACK_
    # SUBMITTED``/``REVIEWED`` — § ``ProgressStatus``).
    COMPLETED = "completed"
