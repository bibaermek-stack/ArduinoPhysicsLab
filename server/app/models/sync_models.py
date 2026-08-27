"""SQLAlchemy ORM models — Cloud Sync server-side entities (Offline-First
+ Cloud Sync Foundation фазасы, §22 "First Entity Scope").

Барлық entity ``sync_id`` (клиенттің ``domain.entities.sync_state``
докстрингіндегі БІРДЕЙ UUID) бойынша PRIMARY KEY-мен сақталады —
клиенттің жергілікті SQLite integer/жол PK-і ЕШҚАШАН серверге
экспортталмайды (§2 "Do NOT expose database autoincrement IDs as
global cloud identifiers").

``server_revision`` әр сәтті upsert сайын серверде АВТОМАТТЫ артады
(§19 "Conflict Strategy": "server authoritative by version" — клиент
ЕШҚАШАН бұл мәнді ӨЗІ орната алмайды, тек сервер жауабынан оқиды).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TeacherRecord(Base):
    __tablename__ = "sync_teachers"

    sync_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # § "do not send raw teacher PIN... unnecessarily" — БҰЛ ӘЛІ ХЭШ (SHA-256),
    # ЕШҚАШАН ашық мәтін ЕМЕС; синхрондаудың ӨЗІ (§12 "Offline Login")
    # басқа құрылғыда дәл СОЛ PIN-мен кіруге мүмкіндік беру үшін керек.
    pin_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    server_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ClassroomRecord(Base):
    __tablename__ = "sync_classrooms"

    sync_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    academic_year: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    server_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class StudentRecord(Base):
    __tablename__ = "sync_students"

    sync_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # § Phase 3 "Bootstrap / First Login": NULL болуы мүмкін (§ ``auth_
    # service.py::authenticate_student()`` — сынып контексті ӘЛІ
    # белгісіз алғашқы TOFU логин кезінде). ``upsert_student()`` (§ Phase 1
    # sync route) ӨЗ валидациясында классрумды әлі де МІНДЕТТІ түрде
    # талап етеді (§ ``RelationshipError``) — тек осы БАСТАПҚЫ bootstrap
    # жолы бос қалдырады, келесі нақты sync push-і НАҚТЫ мәнге ауыстырады.
    classroom_sync_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sync_classrooms.sync_id"), nullable=True
    )
    first_name: Mapped[str] = mapped_column(String(200), nullable=False)
    last_name: Mapped[str] = mapped_column(String(200), nullable=False)
    middle_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    # § "do not send... student access codes unnecessarily" — bұл да
    # мұғалім PIN-мен БІРДЕЙ себеппен синхрондалады (§12 Offline Login —
    # басқа құрылғыда сол кодпен кіру), логталмайды (§27).
    student_code: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    server_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    classroom: Mapped[ClassroomRecord] = relationship()


class SessionRecord(Base):
    """§ Phase 2 (Experiment Session + Results + Feedback Cloud Sync).

    ``experiment_id`` МҮЛДЕ FK ЕМЕС (§25 "do not synchronize the full
    experiment catalog" — ``ModuleRegistry`` код-негізді, серверде
    белгісіз каталог ретінде сақталмайды, тек мөлдір жол ретінде).
    Raw ``measurements`` Phase 2-де СИНХРОНДАЛМАЙДЫ (§27) — бұл жазба
    тек сессия МЕТАДАТАСЫН тасиды.
    """

    __tablename__ = "sync_sessions"

    sync_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(String(100), nullable=False)
    experiment_title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    experiment_display_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    measurement_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    server_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class SessionStudentLinkRecord(Base):
    """§4 "Student <-> Session Link": ``session_sync_id`` ӘДЕЙІ FK ЕМЕС
    (§ ``server/app/services/sync_service.py`` докстрингі — жергілікті
    домен ЕШБІР сессия жазбасы жоқ байланысты да заңды деп таниды,
    § ``derive_status(has_link=True, measurement_count=0)`` ->
    ``IN_PROGRESS``). ``student_sync_id``/``classroom_sync_id`` — НАҚТЫ
    FK, себебі Phase 1 push реті бойынша олар ӘРҚАШАН алдын ала бар."""

    __tablename__ = "sync_session_links"

    session_sync_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    student_sync_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sync_students.sync_id"), nullable=False
    )
    classroom_sync_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sync_classrooms.sync_id"), nullable=False
    )
    experiment_id: Mapped[str] = mapped_column(String(100), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    server_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class FeedbackResultRecord(Base):
    """§5/§6 "Feedback + Teacher Assessment Sync": клиенттегі БІР
    физикалық ``experiment_feedback`` жолымен БІРДЕЙ дизайн — ЕКІ
    тәуелсіз синхрондалатын жарты (оқушы авторлық/мұғалім бағалары)
    БІР серверлік жолда, ӘРҚАЙСЫСЫНЫҢ ӨЗ ``updated_at``/``server_
    revision`` жұбымен (§ ``sqlite_feedback_repository.py`` докстрингі
    — "екі жазба тәуелсіз шақырылады, бірінің жазуы екіншісінің
    деректерін ЕШҚАШАН жоймайды", сол принцип сервер жағында да
    сақталады, § ``sync_service.py::upsert_feedback_result()``/
    ``upsert_teacher_assessment()``)."""

    __tablename__ = "sync_feedback_results"

    sync_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    is_draft: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    level1_answers_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    level1_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    level1_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    level1_percentage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    level2_answers_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    level3_answers_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    self_assessment: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    # § "onupdate=_utcnow" ӘДЕЙІ ЖОҚ (Phase 1-дегі басқа модельдерден
    # айырмашылығы): SQLAlchemy-дің onupdate ЖОЛДЫҢ КЕЗ-КЕЛГЕН UPDATE-і
    # сайын іске қосылады, тіпті ``upsert_teacher_assessment()`` тек
    # teacher_* бағандарын өзгертсе де — бұл ``updated_at``-ты (осы
    # жарты, оқушы авторлық) жалған түрде жаңартып, ``pull_feedback_
    # results()``-ты қажетсіз қайта қайтарар еді (§ керісінше де СОЛ
    # себеппен ``teacher_updated_at``-та да onupdate жоқ). Тек ӘРБІР
    # upsert функциясының ӨЗІ, НАҚТЫ өз жартысы үшін ғана айқын
    # орнатады (§ ``upsert_feedback_result()``/``upsert_teacher_
    # assessment()``).
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    server_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    teacher_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    teacher_comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    teacher_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    teacher_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    teacher_server_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)


class TeacherClassroomLinkRecord(Base):
    """Бір мұғалімнің ТОЛЫҚ тағайындалған сынып жиыны (§ клиент дизайны
    — жеке байланыс жазбасы ЕМЕС, "мұғалімнің меншігі" ретінде
    синхрондалады, § ``sqlite_teacher_repository.py`` докстрингі)."""

    __tablename__ = "sync_teacher_classrooms"

    teacher_sync_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sync_teachers.sync_id"), primary_key=True
    )
    # SQLite/Postgres екеуінде де жұмыс істеу үшін JSON массив жол
    # ретінде сақталады (§ "do not overcomplicate" — арнайы M2M кестесі
    # осы фазада артық).
    classroom_sync_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    server_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class MeasurementBatchRecord(Base):
    """§ Phase 4 (Raw Arduino Measurement Cloud Sync). ``sync_sessions``
    сияқты ЖЕКЕ, тұрақты ``sync_id`` (клиенттің ``batch_sync_id``,
    UUID) — БІР сессияда БІРНЕШЕ, қатар pending batch болуы мүмкін
    (§ ``outbox``-тың ``UNIQUE(entity_type, entity_sync_id)`` шектеуі
    осыны талап етеді, § клиент докстрингі). ``session_sync_id`` НАҚТЫ
    FK — "measurement batches depend on ExperimentSession; must never
    precede it" (§ ``PUSH_ORDER``/§ авторизация: ``session_sync_id``
    арқылы иелену/қолжетімділік шешіледі, клиент айтқан меншік ЕШҚАШАН
    тікелей сенілмейді, § ``authorization.py::current_user_can_access_
    session()``).

    Batch МАЗМҰНЫ (``sequence_start``/``sequence_end``/``sample_count``)
    құрылғаннан кейін ӨЗГЕРМЕЙДІ (§ "same batch_sync_id uploaded once or
    twenty times must produce the same final server state") — сол
    себепті ``upsert_measurement_batch()`` (§ ``sync_service.py``) БАР
    жазбаны ЕШҚАШАН қайта жазбайды, тек revision-ды қайтарады.
    """

    __tablename__ = "sync_measurement_batches"

    sync_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_sync_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sync_sessions.sync_id"), nullable=False
    )
    sequence_start: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence_end: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    server_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    measurements: Mapped[list["MeasurementRecord"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=False, order_by="MeasurementRecord.sequence_no"
    )


class MeasurementRecord(Base):
    """§ Phase 4: НАҚТЫ raw Arduino өлшеу жолдары — ЖЕКЕ ``sync_id``
    ЖОҚ (§ "the durable synchronization unit should be a measurement
    batch/chunk, not individual measurement rows"). ``id`` — сервер-
    ішкі ғана autoincrement (§ "Do NOT expose database autoincrement
    IDs as global cloud identifiers" ЕШБІР қатысы жоқ, себебі бұл ID
    клиентке ЕШҚАШАН қайтарылмайды/қолданылмайды — жол тек ``batch_
    sync_id`` арқылы қауіпсіз идемпотентті түрде жазылады/оқылады).

    ``UNIQUE(session_sync_id, sequence_no)`` — клиенттің ``idx_
    measurements_session_sequence_unique``-мен БІРДЕЙ инвариант,
    сервер жағында да ҚАЙТАЛАМА pull/push-ты ЕШБІР дубликат жасамай
    қауіпсіз ete алады (§ "idempotency HARD requirement").
    """

    __tablename__ = "sync_measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_sync_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sync_measurement_batches.sync_id"), nullable=False
    )
    # § Денормализация: батч сілтемесінсіз-ақ сессия бойынша тікелей
    # сұрау/авторизация тексеруі үшін (§ ``sync_service.py`` "second
    # device reconstruction" оқу жолы — тек ``session_sync_id`` арқылы
    # барлық measurement-ді ретімен алады, батч шекараларына тәуелсіз).
    session_sync_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    values_json: Mapped[str] = mapped_column(Text, nullable=False)
    derived_values_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    __table_args__ = (
        UniqueConstraint("session_sync_id", "sequence_no", name="uq_measurement_session_sequence"),
    )


class TeacherNoteRecord(Base):
    """§ Phase 7 (Teacher Actions, Feedback Delivery, and Session
    History). Бір бағытты (тек мұғалім авторлық) — ``FeedbackResultRecord``-
    тегідей екі жартылы split ЖОҚ, себебі ``read_at`` ЖЕРГІЛІКТІ-тек
    (§ ``domain/entities/teacher_note.py`` докстрингі — синхрондалмайды,
    сондықтан бұл кестеде МҮЛДЕ ЖОҚ). ``session_sync_id``/``experiment_id``
    ЕРІКТІ контекст — қатаң FK ЕМЕС (§ ``SessionRecord.experiment_id``-
    мен БІРДЕЙ себеп, бір пікір белгілі бір сессияға қатысты болмауы да
    мүмкін)."""

    __tablename__ = "sync_teacher_notes"

    sync_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    teacher_sync_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sync_teachers.sync_id"), nullable=False
    )
    student_sync_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sync_students.sync_id"), nullable=False
    )
    classroom_sync_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sync_classrooms.sync_id"), nullable=False
    )
    experiment_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    session_sync_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    server_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
