"""sync_engine — Cloud Sync orchestration (Offline-First + Cloud Sync
Foundation фазасы, §16 "Background Sync").

Таза Python — ЕШБІР Qt/HTTP тәуелділігі жоқ (§ "UI should continue to
read/write through existing repository/service abstractions... Do NOT
scatter requests/network code across pages" принципінің НАҚТЫ орталық
нүктесі). ``infrastructure/sync/sync_worker.py`` осы класты ТЕК
``QThread`` ішінде шақырады — бизнес-логиканың ӨЗІ мұнда, толық Qt-сыз
тексерілуге қолжетімді.

§27 "Logging": бұл модуль payload МАЗМҰНЫН (аты-жөні/PIN хэші/оқушы
коды/access token) ЕШҚАШАН логтамайды — тек ``entity_type``/саны/қате
мәтіні.

§ Phase 3 (Production Authentication + Authorization): ``get_active_
role_and_sync_id``/``get_cached_token``/``set_cached_token`` — ЕРІКТІ
(§ established "optional dependency with safe default" паттерні,
``session_repository`` Phase 2-мен БІРДЕЙ) — берілмесе, аутентификация
orchestration-ы толығымен ӨШІРІЛГЕН (ескі fake-client unit тесттер
ЕШБІР өзгеріссіз жұмыс істейді). Берілсе:

    ``run_sync()`` → ``_ensure_authenticated()`` (кэштелген токен
    жарамды ма, солай болмаса жергілікті сақталған pin_hash/student_
    code-мен жаңа логин) → push/pull. ``SyncAuthenticationError``
    (401) кездессе бір рет қайта логин көреді; ``SyncAuthorizationError``
    (403) ешқашан жедел қайталанбайды (§8).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from domain.entities.sync_status import SyncStatus
from domain.interfaces.i_active_teacher_repository import IActiveTeacherRepository
from domain.interfaces.i_classroom_repository import IClassroomRepository
from domain.interfaces.i_feedback_repository import IFeedbackRepository
from domain.interfaces.i_session_repository import ISessionRepository
from domain.interfaces.i_student_progress_repository import IStudentProgressRepository
from domain.interfaces.i_student_repository import IStudentRepository
from domain.interfaces.i_sync_api_client import (
    ISyncApiClient,
    SyncAuthenticationError,
    SyncAuthorizationError,
)
from domain.interfaces.i_sync_outbox_repository import ISyncOutboxRepository
from domain.interfaces.i_teacher_note_repository import ITeacherNoteRepository
from domain.interfaces.i_teacher_repository import ITeacherRepository
from domain.services.sync_backoff import compute_next_retry_at
from domain.interfaces.i_measurement_batch_repository import IMeasurementBatchRepository
from domain.services.sync_payload import (
    ENTITY_TYPE_CLASSROOM,
    ENTITY_TYPE_FEEDBACK_RESULT,
    ENTITY_TYPE_MEASUREMENT_BATCH,
    ENTITY_TYPE_SESSION,
    ENTITY_TYPE_SESSION_STUDENT_LINK,
    ENTITY_TYPE_STUDENT,
    ENTITY_TYPE_TEACHER,
    ENTITY_TYPE_TEACHER_ASSESSMENT,
    ENTITY_TYPE_TEACHER_CLASSROOM,
    ENTITY_TYPE_TEACHER_NOTE,
    PUSH_ORDER,
    classroom_to_payload,
    payload_to_classroom,
    payload_to_student,
    payload_to_teacher,
    student_to_payload,
    teacher_classroom_to_payload,
    teacher_to_payload,
)

_sync_logger = logging.getLogger("apl.sync")

_DEFAULT_PULL_LIMIT = 500
_ROLE_TEACHER = "teacher"
# §8 "403 behavior": "do NOT endlessly retry an unauthorized write" —
# қалыпты 1/5/15/30 минуттық желі-қатесі кестесінен (§ ``sync_backoff.
# py``) ӘДЕЙІ ұзақ, себебі рұқсат бас тартылуы жиі қайталанып
# тексерілуге тұрарлық ЖЕДЕЛ жағдай ЕМЕС.
_AUTHORIZATION_DENIED_RETRY_DELAY = timedelta(hours=24)


@dataclass(frozen=True)
class SyncResult:
    status: SyncStatus
    pushed: int = 0
    pulled: int = 0
    errors: tuple[str, ...] = field(default_factory=tuple)


class SyncEngine:
    def __init__(
        self,
        classroom_repository: IClassroomRepository,
        student_repository: IStudentRepository,
        teacher_repository: ITeacherRepository,
        sync_outbox_repository: ISyncOutboxRepository,
        api_client: ISyncApiClient,
        get_pull_cursor,
        set_pull_cursor,
        session_repository: ISessionRepository | None = None,
        student_progress_repository: IStudentProgressRepository | None = None,
        feedback_repository: IFeedbackRepository | None = None,
        get_active_role_and_sync_id=None,
        get_cached_token=None,
        set_cached_token=None,
        measurement_batch_repository: IMeasurementBatchRepository | None = None,
        teacher_note_repository: ITeacherNoteRepository | None = None,
    ) -> None:
        self._classroom_repository = classroom_repository
        self._student_repository = student_repository
        self._teacher_repository = teacher_repository
        self._sync_outbox_repository = sync_outbox_repository
        self._api_client = api_client
        self._get_pull_cursor = get_pull_cursor
        self._set_pull_cursor = set_pull_cursor
        # § Phase 2 (Experiment Session + Results + Feedback Cloud Sync):
        # ЕРІКТІ параметрлер (§ established "optional dependency with
        # safe default" паттерні, ``sync_outbox_repository`` Phase 1-мен
        # БІРДЕЙ) — берілмесе, тек session/feedback entity_type-тары
        # ЕШҚАШАН push/pull етілмейді (Teacher/Classroom/Student/
        # Teacher-Classroom бұрынғыдай толық жұмыс істейді).
        self._session_repository = session_repository
        self._student_progress_repository = student_progress_repository
        self._feedback_repository = feedback_repository
        # § Phase 3: ЕРІКТІ — берілмесе аутентификация orchestration-ы
        # толығымен өшірілген (§ модуль докстрингі).
        self._get_active_role_and_sync_id = get_active_role_and_sync_id
        self._get_cached_token = get_cached_token
        self._set_cached_token = set_cached_token
        # § Phase 4 (Raw Arduino Measurement Cloud Sync): ЕРІКТІ —
        # берілмесе, ``measurement_batch`` entity_type ЕШҚАШАН push/pull
        # етілмейді (§ established "optional dependency with safe
        # default" паттерні, ``session_repository`` Phase 2-мен БІРДЕЙ).
        self._measurement_batch_repository = measurement_batch_repository
        # § Phase 7 (Teacher Actions, Feedback Delivery, and Session
        # History): ЕРІКТІ — берілмесе, ``teacher_note`` entity_type
        # ЕШҚАШАН push/pull етілмейді (§ established "optional dependency
        # with safe default" паттерні).
        self._teacher_note_repository = teacher_note_repository

    def run_sync(self, now: datetime | None = None) -> SyncResult:
        now = now or datetime.now(timezone.utc)
        _sync_logger.info("sync start")

        if not self._api_client.check_health():
            _sync_logger.info("sync skipped: server unreachable (offline)")
            return SyncResult(status=SyncStatus.OFFLINE)

        if not self._ensure_authenticated(now):
            _sync_logger.info("sync skipped: authentication required")
            return SyncResult(status=SyncStatus.AUTH_REQUIRED)

        pushed, push_errors, push_auth_lost = self._push_pending(now)
        if push_auth_lost:
            _sync_logger.info("sync end: authentication required (push)")
            return SyncResult(status=SyncStatus.AUTH_REQUIRED, pushed=pushed, errors=tuple(push_errors))

        pulled, pull_errors, pull_auth_lost = self._pull_all()
        if pull_auth_lost:
            _sync_logger.info("sync end: authentication required (pull)")
            return SyncResult(
                status=SyncStatus.AUTH_REQUIRED, pushed=pushed, pulled=pulled,
                errors=tuple(push_errors) + tuple(pull_errors),
            )

        errors = tuple(push_errors) + tuple(pull_errors)
        status = SyncStatus.SYNC_ERROR if errors else SyncStatus.SYNCED
        _sync_logger.info(
            "sync end: status=%s pushed=%d pulled=%d error_count=%d", status.value, pushed, pulled, len(errors)
        )
        return SyncResult(status=status, pushed=pushed, pulled=pulled, errors=errors)

    # ---- Authentication (Phase 3) -------------------------------------------

    def _ensure_authenticated(self, now: datetime) -> bool:
        """``True`` — sync жалғастыра алады (токен орнатылды НЕМЕСЕ
        auth orchestration өшірілген/ешкім жергілікті кірмеген — § ескі
        мінез-құлыққа құлайды, сервер өзі 401 қайтарса қалыпты қатеге
        ұқсас өңделеді). ``False`` — жергілікті credential серверде
        қабылданбады (§ ``AUTH_REQUIRED``)."""
        if self._get_active_role_and_sync_id is None:
            return True
        identity = self._get_active_role_and_sync_id()
        if identity is None:
            return True
        role, sync_id = identity

        cached = self._get_cached_token() if self._get_cached_token is not None else None
        if cached is not None:
            token, expires_at, cached_role, cached_sync_id = cached
            if cached_role == role and cached_sync_id == sync_id and expires_at > now:
                self._api_client.set_auth_token(token)
                return True

        return self._login(role, sync_id)

    def _login(self, role: str, sync_id: str) -> bool:
        credential = self._resolve_local_credential(role, sync_id)
        if credential is None:
            return True  # § жергілікті жазба табылмады — ескі мінез-құлыққа құлайды

        try:
            auth_result = (
                self._api_client.login_as_teacher(sync_id, credential)
                if role == _ROLE_TEACHER
                else self._api_client.login_as_student(sync_id, credential)
            )
        except Exception as exc:  # noqa: BLE001 - желі/сервер қатесі күтілетін жол
            _sync_logger.warning("login failed: %s", exc)
            return False

        if auth_result is None:
            _sync_logger.warning("login rejected: invalid local credential for role=%s", role)
            return False

        self._api_client.set_auth_token(auth_result.token)
        if self._set_cached_token is not None:
            self._set_cached_token(auth_result.token, auth_result.expires_at, role, sync_id)
        return True

    def _resolve_local_credential(self, role: str, sync_id: str) -> str | None:
        if role == _ROLE_TEACHER:
            teacher = self._teacher_repository.get(sync_id)
            return teacher.pin_hash if teacher is not None else None
        student = self._student_repository.get(sync_id)
        return student.student_code if student is not None else None

    def _reauthenticate(self, now: datetime) -> bool:
        """§8 "401 behavior: attempt safe token refresh/re-authentication
        if possible" — кэшті елемей, ТІКЕЛЕЙ жаңа логин."""
        if self._get_active_role_and_sync_id is None:
            return False
        identity = self._get_active_role_and_sync_id()
        if identity is None:
            return False
        role, sync_id = identity
        return self._login(role, sync_id)

    # ---- Push (outbox -> server) -------------------------------------------

    def _push_pending(self, now: datetime) -> tuple[int, list[str], bool]:
        pushed = 0
        errors: list[str] = []

        entries_by_type: dict[str, list] = defaultdict(list)
        for entry in self._sync_outbox_repository.list_due(now):
            entries_by_type[entry.entity_type].append(entry)

        for entity_type in PUSH_ORDER:
            type_entries = entries_by_type.get(entity_type, [])
            if not type_entries:
                continue

            payloads: list[dict] = []
            entry_by_sync_id = {}
            for entry in type_entries:
                payload = self._build_push_payload(entity_type, entry.entity_sync_id)
                if payload is None:
                    # Жергілікті жазба ЕНДІ жоқ (сирек, мыс. репозиторий
                    # тестерде тазаланды) — outbox-та мәнсіз қалдырмаймыз.
                    self._sync_outbox_repository.mark_success(entry.id)
                    continue
                payloads.append(payload)
                entry_by_sync_id[entry.entity_sync_id] = entry

            if not payloads:
                continue

            try:
                results = self._api_client.push(entity_type, payloads)
            except SyncAuthorizationError as exc:
                # §8 "403": ешқашан жедел қайталанбайды, БІРАҚ outbox-та
                # қалады (§ "preserve enough diagnostic state").
                _sync_logger.warning("push forbidden for entity_type=%s", entity_type)
                far_retry = now + _AUTHORIZATION_DENIED_RETRY_DELAY
                for entry in type_entries:
                    self._sync_outbox_repository.mark_failure(entry.id, str(exc), far_retry)
                errors.append(f"{entity_type}: forbidden")
                continue
            except SyncAuthenticationError as exc:
                if self._reauthenticate(now):
                    try:
                        results = self._api_client.push(entity_type, payloads)
                    except Exception as retry_exc:  # noqa: BLE001
                        _sync_logger.warning(
                            "push still failing after re-auth for entity_type=%s: %s", entity_type, retry_exc
                        )
                        for entry in type_entries:
                            next_retry = compute_next_retry_at(entry.attempt_count, now)
                            self._sync_outbox_repository.mark_failure(entry.id, str(retry_exc), next_retry)
                        return pushed, errors, True
                else:
                    _sync_logger.warning("re-authentication failed for entity_type=%s: %s", entity_type, exc)
                    for entry in type_entries:
                        next_retry = compute_next_retry_at(entry.attempt_count, now)
                        self._sync_outbox_repository.mark_failure(entry.id, str(exc), next_retry)
                    return pushed, errors, True
            except Exception as exc:  # noqa: BLE001 - желі/сервер қатесі күтілетін жол
                _sync_logger.warning("push failed for entity_type=%s: %s", entity_type, exc)
                for entry in type_entries:
                    next_retry = compute_next_retry_at(entry.attempt_count, now)
                    self._sync_outbox_repository.mark_failure(entry.id, str(exc), next_retry)
                errors.append(f"{entity_type}: {exc}")
                continue

            for result in results:
                entry = entry_by_sync_id.get(result.sync_id)
                if entry is None:
                    continue
                if result.status == "upserted":
                    self._mark_local_synced(entity_type, result.sync_id, result.server_revision or 0)
                    self._sync_outbox_repository.mark_success(entry.id)
                    pushed += 1
                else:
                    next_retry = compute_next_retry_at(entry.attempt_count, now)
                    self._sync_outbox_repository.mark_failure(entry.id, result.error, next_retry)
                    errors.append(f"{entity_type}:{result.sync_id}: {result.error}")

        return pushed, errors, False

    def _build_push_payload(self, entity_type: str, sync_id: str) -> dict | None:
        if entity_type == ENTITY_TYPE_TEACHER:
            teacher = self._teacher_repository.get(sync_id)
            return teacher_to_payload(teacher) if teacher is not None else None
        if entity_type == ENTITY_TYPE_CLASSROOM:
            classroom = self._classroom_repository.get(sync_id)
            return classroom_to_payload(classroom) if classroom is not None else None
        if entity_type == ENTITY_TYPE_STUDENT:
            student = self._student_repository.get(sync_id)
            return student_to_payload(student) if student is not None else None
        if entity_type == ENTITY_TYPE_TEACHER_CLASSROOM:
            teacher = self._teacher_repository.get(sync_id)
            if teacher is None:
                return None
            classroom_ids = self._teacher_repository.list_assigned_classroom_ids(teacher.id)
            return teacher_classroom_to_payload(teacher.sync_id, classroom_ids, datetime.now(timezone.utc))
        if entity_type == ENTITY_TYPE_SESSION:
            if self._session_repository is None:
                return None
            return self._session_repository.get_sync_payload(sync_id)
        if entity_type == ENTITY_TYPE_SESSION_STUDENT_LINK:
            if self._student_progress_repository is None:
                return None
            return self._student_progress_repository.get_link_sync_payload(sync_id)
        if entity_type == ENTITY_TYPE_FEEDBACK_RESULT:
            if self._feedback_repository is None:
                return None
            return self._feedback_repository.get_feedback_sync_payload(sync_id)
        if entity_type == ENTITY_TYPE_TEACHER_ASSESSMENT:
            if self._feedback_repository is None:
                return None
            return self._feedback_repository.get_teacher_assessment_sync_payload(sync_id)
        if entity_type == ENTITY_TYPE_MEASUREMENT_BATCH:
            if self._measurement_batch_repository is None:
                return None
            return self._measurement_batch_repository.get_batch_sync_payload(sync_id)
        if entity_type == ENTITY_TYPE_TEACHER_NOTE:
            if self._teacher_note_repository is None:
                return None
            return self._teacher_note_repository.get_note_sync_payload(sync_id)
        return None

    def _mark_local_synced(self, entity_type: str, sync_id: str, server_revision: int) -> None:
        if entity_type == ENTITY_TYPE_TEACHER:
            self._teacher_repository.mark_synced(sync_id, server_revision)
        elif entity_type == ENTITY_TYPE_CLASSROOM:
            self._classroom_repository.mark_synced(sync_id, server_revision)
        elif entity_type == ENTITY_TYPE_STUDENT:
            self._student_repository.mark_synced(sync_id, server_revision)
        # ENTITY_TYPE_TEACHER_CLASSROOM: § тағайындау жиынының ӨЗІНДЕ
        # жеке sync_state бағаны ЖОҚ (§ database.py дизайны).
        elif entity_type == ENTITY_TYPE_SESSION and self._session_repository is not None:
            self._session_repository.mark_session_synced(sync_id, server_revision)
        elif (
            entity_type == ENTITY_TYPE_SESSION_STUDENT_LINK
            and self._student_progress_repository is not None
        ):
            self._student_progress_repository.mark_link_synced(sync_id, server_revision)
        elif entity_type == ENTITY_TYPE_FEEDBACK_RESULT and self._feedback_repository is not None:
            self._feedback_repository.mark_feedback_synced(sync_id, server_revision)
        elif entity_type == ENTITY_TYPE_TEACHER_ASSESSMENT and self._feedback_repository is not None:
            self._feedback_repository.mark_teacher_assessment_synced(sync_id, server_revision)
        elif (
            entity_type == ENTITY_TYPE_MEASUREMENT_BATCH
            and self._measurement_batch_repository is not None
        ):
            self._measurement_batch_repository.mark_batch_synced(sync_id, server_revision)
        elif entity_type == ENTITY_TYPE_TEACHER_NOTE and self._teacher_note_repository is not None:
            self._teacher_note_repository.mark_note_synced(sync_id, server_revision)

    # ---- Pull (server -> local) ---------------------------------------------

    def _pull_all(self) -> tuple[int, list[str], bool]:
        pulled = 0
        errors: list[str] = []
        now = datetime.now(timezone.utc)

        for entity_type in PUSH_ORDER:
            cursor = self._get_pull_cursor(entity_type)
            try:
                result = self._api_client.pull(entity_type, cursor, _DEFAULT_PULL_LIMIT)
            except SyncAuthorizationError as exc:
                # § pull-да 403 (мыс. рөлге мүлде рұқсат етілмеген entity_
                # type) — сол entity_type-ты жай өткізіп жібереді, БІРАҚ
                # бүкіл циклды тоқтатпайды (§ pull-дың ӨЗІ "filtered, not
                # rejected" дизайны — 403 сирек, тек симметрия үшін).
                _sync_logger.warning("pull forbidden for entity_type=%s", entity_type)
                errors.append(f"{entity_type} pull: forbidden")
                continue
            except SyncAuthenticationError as exc:
                if self._reauthenticate(now):
                    try:
                        result = self._api_client.pull(entity_type, cursor, _DEFAULT_PULL_LIMIT)
                    except Exception as retry_exc:  # noqa: BLE001
                        _sync_logger.warning(
                            "pull still failing after re-auth for entity_type=%s: %s", entity_type, retry_exc
                        )
                        return pulled, errors, True
                else:
                    _sync_logger.warning("re-authentication failed for entity_type=%s: %s", entity_type, exc)
                    return pulled, errors, True
            except Exception as exc:  # noqa: BLE001
                _sync_logger.warning("pull failed for entity_type=%s: %s", entity_type, exc)
                errors.append(f"{entity_type} pull: {exc}")
                continue

            for item in result.items:
                self._apply_pulled_item(entity_type, item)
                pulled += 1
            self._set_pull_cursor(entity_type, result.server_time)

        return pulled, errors, False

    def _apply_pulled_item(self, entity_type: str, item: dict) -> None:
        if entity_type == ENTITY_TYPE_TEACHER:
            self._teacher_repository.apply_remote_upsert(payload_to_teacher(item))
        elif entity_type == ENTITY_TYPE_CLASSROOM:
            self._classroom_repository.apply_remote_upsert(payload_to_classroom(item))
        elif entity_type == ENTITY_TYPE_STUDENT:
            self._student_repository.apply_remote_upsert(payload_to_student(item))
        elif entity_type == ENTITY_TYPE_TEACHER_CLASSROOM:
            self._teacher_repository.apply_remote_assignment(
                item["teacher_sync_id"], tuple(item["classroom_sync_ids"])
            )
        elif entity_type == ENTITY_TYPE_SESSION and self._session_repository is not None:
            self._session_repository.apply_remote_session(item)
        elif (
            entity_type == ENTITY_TYPE_SESSION_STUDENT_LINK
            and self._student_progress_repository is not None
        ):
            self._student_progress_repository.apply_remote_link(item)
        elif entity_type == ENTITY_TYPE_FEEDBACK_RESULT and self._feedback_repository is not None:
            self._feedback_repository.apply_remote_feedback(item)
        elif entity_type == ENTITY_TYPE_TEACHER_ASSESSMENT and self._feedback_repository is not None:
            self._feedback_repository.apply_remote_teacher_assessment(item)
        elif (
            entity_type == ENTITY_TYPE_MEASUREMENT_BATCH
            and self._measurement_batch_repository is not None
        ):
            self._measurement_batch_repository.apply_remote_batch(item)
        elif entity_type == ENTITY_TYPE_TEACHER_NOTE and self._teacher_note_repository is not None:
            self._teacher_note_repository.apply_remote_note(item)
