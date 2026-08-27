"""SyncState — жергілікті жазбаның Cloud Sync-пен қатысты күйі
(Offline-First + Cloud Sync Foundation фазасы).

``UserRole``-мен БІРДЕЙ typed enum конвенциясы. ЕСКЕРТУ: бұл ``ui``
деңгейіндегі ``ProgressStatus``-пен (эксперимент прогресі) МҮЛДЕ БӨЛЕК
концепция — синхрондау күйі ешқашан ProgressStatus-пен араласпайды
(§ "Do not reuse UI ProgressStatus for synchronization status").

Ең кіші сенімді күй моделі (§ "smallest robust state model"):
- ``PENDING_UPLOAD`` — жергілікті жазылған, серверге әлі жіберілмеген
  (жаңа жазбаның ӘДЕПКІ бастапқы күйі).
- ``SYNCED`` — сервер растаған соңғы нұсқа.
- ``PENDING_DELETE`` — жергілікті мұрағатталған/белсенді емес етілген,
  сол өзгеріс серверге әлі жіберілмеген.
- ``CONFLICT`` — сервер қайшылықты нұсқа хабарлаған, қолмен/келесі
  синхрондау стратегиясымен шешілуі керек.
- ``ERROR`` — соңғы синхрондау әрекеті сәтсіз аяқталды (желі/сервер
  қатесі), outbox қайталап көреді.
"""

from enum import Enum


class SyncState(Enum):
    PENDING_UPLOAD = "pending_upload"
    SYNCED = "synced"
    PENDING_DELETE = "pending_delete"
    CONFLICT = "conflict"
    ERROR = "error"
