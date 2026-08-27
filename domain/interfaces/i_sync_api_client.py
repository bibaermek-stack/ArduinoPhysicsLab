"""ISyncApiClient — қашықтағы Cloud Sync API-мен байланысатын клиент
интерфейсі (Offline-First + Cloud Sync Foundation фазасы).

``domain/services/sync_engine.py`` ЕШҚАШАН HTTP/желі бөлшектерін
білмейді — тек осы таза интерфейс арқылы (§ "UI should continue to
read/write through existing repository/service abstractions"
принципімен БІРДЕЙ, тек HTTP қабатына қолданылған). Нақты іске асыру
``infrastructure/sync/http_sync_api_client.py``-де (§ ``httpx``,
жобада ӘЛДЕҚАШАН бар тәуелділік).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class PushItemResult:
    sync_id: str
    status: str  # "upserted" | "error"
    server_revision: int | None = None
    error: str = ""


@dataclass(frozen=True)
class PullResult:
    items: tuple[dict, ...]
    server_time: datetime


@dataclass(frozen=True)
class AuthResult:
    """§ Phase 3: ``/api/v1/auth/{teacher,student}-login`` жетістік
    жауабы."""

    token: str
    expires_at: datetime
    sync_id: str
    role: str


class SyncAuthenticationError(Exception):
    """§8 "401 behavior": токен жоқ/мерзімі өткен/жарамсыз. ``SyncEngine``
    осыны бір рет қайта логин/қайталау үшін ұстайды — outbox/жергілікті
    дерек ЕШҚАШАН осы қатеге байланысты жойылмайды."""


class SyncAuthorizationError(Exception):
    """§8 "403 behavior": аутентификацияланған, БІРАҚ бұл НАҚТЫ жазуға
    рұқсат жоқ. ЕШҚАШАН шексіз қайталанбайды (§ ``SyncEngine`` ұзақ
    backoff қолданады, қалыпты желі-қатесі кестесін ЕМЕС)."""


class ISyncApiClient(ABC):
    @abstractmethod
    def check_health(self) -> bool:
        """§13 "Connectivity Service" — тез timeout, ешбір exception
        сыртқа шықпайды (желі қатесі кезінде ``False`` қайтарады)."""
        raise NotImplementedError

    @abstractmethod
    def login_as_teacher(self, sync_id: str, pin_hash: str) -> AuthResult | None:
        """§2 "Online Authentication": сәтсіз (қате credential, 401)
        болса ``None`` қайтарады — желі/сервер қатесі әдеттегідей
        exception ретінде таралады."""
        raise NotImplementedError

    @abstractmethod
    def login_as_student(self, sync_id: str, student_code: str) -> AuthResult | None:
        raise NotImplementedError

    @abstractmethod
    def set_auth_token(self, token: str | None) -> None:
        """Кейінгі ``push()``/``pull()`` шақыруларына ``Authorization:
        Bearer <token>`` тақырыбын тіркейді. ``None`` — тақырыпты алып
        тастайды (§ "logout/token clearing behavior")."""
        raise NotImplementedError

    @abstractmethod
    def push(self, entity_type: str, payloads: list[dict]) -> list[PushItemResult]:
        """§8: 401 -> ``SyncAuthenticationError``, 403 -> ``Sync
        AuthorizationError``, басқа 4xx/5xx -> қалыпты HTTP exception."""
        raise NotImplementedError

    @abstractmethod
    def pull(self, entity_type: str, updated_since: datetime | None, limit: int) -> PullResult:
        raise NotImplementedError
