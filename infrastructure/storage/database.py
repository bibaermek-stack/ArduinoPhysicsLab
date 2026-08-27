"""database — Data Journal SQLite схемасын инициализациялау және
пайдаланушының application-data қалтасындағы дефолт DB жолын анықтау.

Миграция framework-і ЖОҚ (V1 үшін артық) — тек идемпотентті
``CREATE TABLE IF NOT EXISTS`` DDL.

§ Offline-First + Cloud Sync Foundation (§4 "Do NOT break existing
database"): бірінші рет ``CREATE TABLE``-ден тыс ЖЕКЕ ALTER TABLE
негізді идемпотентті миграция қажет болды — ``sync_id``/``sync_state``/
``server_revision`` бағандары ЕНДІ БАР ``teachers``/``classrooms``/
``students`` кестелеріне қосылады (§ ``_add_column_if_missing()``,
``PRAGMA table_info`` арқылы баған бар-жоғын тексеріп, тек ЖОҚ болса
ғана ``ALTER TABLE ... ADD COLUMN`` шақырады — қайта шақырылса да
ешбір қате/қайталану жасамайды).
"""

import logging
import shutil
import sqlite3
from pathlib import Path

from PySide6.QtCore import QStandardPaths

_logger = logging.getLogger(__name__)

_DATABASE_FILENAME = "arduino_physics_lab.db"

_SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS experiment_sessions (
        id TEXT PRIMARY KEY,
        experiment_id TEXT NOT NULL,
        experiment_display_number INTEGER,
        experiment_title TEXT NOT NULL,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        status TEXT NOT NULL,
        measurement_count INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS measurements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        sequence_no INTEGER NOT NULL,
        timestamp TEXT NOT NULL,
        values_json TEXT NOT NULL,
        derived_values_json TEXT NOT NULL,
        warnings_json TEXT NOT NULL,
        FOREIGN KEY(session_id) REFERENCES experiment_sessions(id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_measurements_session_id ON measurements(session_id)",
    # Phase 39A: үш деңгейлі кері байланыс/бағалау — raw measurements-тен
    # МҮЛДЕ БӨЛЕК кесте (сессияға БІР жол). Идемпотентті аддитивті DDL —
    # ескі дерекқор файлдары (бұл кесте жоқ) осы жол арқылы ЕШБІР
    # деректі жоймай/қайта жазбай ашылады.
    """
    CREATE TABLE IF NOT EXISTS experiment_feedback (
        session_id TEXT PRIMARY KEY,
        experiment_id TEXT NOT NULL,
        is_draft INTEGER NOT NULL,
        level1_answers_json TEXT NOT NULL,
        level1_score INTEGER NOT NULL,
        level1_total INTEGER NOT NULL,
        level1_percentage REAL NOT NULL,
        level2_answers_json TEXT NOT NULL,
        level3_answers_json TEXT NOT NULL,
        self_assessment INTEGER,
        submitted_at TEXT,
        teacher_score INTEGER,
        teacher_comment TEXT,
        teacher_reviewed INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # Phase 39B: сыныптар/оқушылар/белсенді оқушы/сессия-оқушы байланысы —
    # raw measurements/experiment_sessions/experiment_feedback кестелерінен
    # МҮЛДЕ БӨЛЕК, идемпотентті аддитивті DDL (ескі дерекқор файлдары осы
    # жаңа кестелерсіз де қалыпты ашылады, ешбір бар жол өзгертілмейді).
    """
    CREATE TABLE IF NOT EXISTS classrooms (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        academic_year TEXT NOT NULL,
        description TEXT NOT NULL,
        is_archived INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS students (
        id TEXT PRIMARY KEY,
        classroom_id TEXT NOT NULL,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        middle_name TEXT NOT NULL,
        student_code TEXT NOT NULL,
        notes TEXT NOT NULL,
        is_archived INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_students_classroom_id ON students(classroom_id)",
    # Жалғыз жол кестесі (id=1 CHECK) — ағымдағы белсенді оқушы контексті.
    # classroom_id/student_id NULL болуы мүмкін (ешкім таңдалмаған).
    """
    CREATE TABLE IF NOT EXISTS active_student_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        classroom_id TEXT,
        student_id TEXT,
        updated_at TEXT NOT NULL
    )
    """,
    # session_id PK — сессия сәйкестігі on_enter()-де ҚАЛЫПТАСҚАН СӘТТЕ-АҚ
    # (алғашқы өлшеуге дейін) жазылады, experiment_sessions-тегі жолмен
    # ешбір FK тәуелділігі жоқ (соңғысы тек бос емес сессиялар үшін
    # save_session() арқылы кейінірек жазылады).
    """
    CREATE TABLE IF NOT EXISTS session_student_link (
        session_id TEXT PRIMARY KEY,
        student_id TEXT NOT NULL,
        classroom_id TEXT NOT NULL,
        experiment_id TEXT NOT NULL,
        linked_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_session_student_link_student ON session_student_link(student_id)",
    # Phase 20 (Question Bank): бақылау/рефлексия сұрақтары — бұрын тек
    # Python коды ретінде (modules/*/experiments_config.py) сақталатын,
    # ЕШБІР SQLite кестесі жоқ болатын. Идемпотентті аддитивті DDL —
    # ескі дерекқор файлдары осы жаңа кестесіз де қалыпты ашылады.
    # ``options_json``/``correct_option_index`` тек 1-деңгей (тест)
    # сұрағында мәнді (§ MultipleChoiceQuestion), 2/3-деңгейде NULL.
    """
    CREATE TABLE IF NOT EXISTS questions (
        id TEXT PRIMARY KEY,
        experiment_id TEXT NOT NULL,
        level INTEGER NOT NULL,
        prompt TEXT NOT NULL,
        options_json TEXT,
        correct_option_index INTEGER,
        points INTEGER NOT NULL DEFAULT 1,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_questions_experiment_id ON questions(experiment_id)",
    # Multi-Teacher Accounts фазасы: жүйені пайдаланатын мұғалім
    # аккаунттары — идемпотентті аддитивті DDL (ескі дерекқор файлдары
    # осы жаңа кестелерсіз де қалыпты ашылады, ешбір бар жол
    # өзгертілмейді). PIN мәтіні ЕШҚАШАН сақталмайды — тек ``pin_hash``
    # (§ ``domain/services/teacher_pin.py::hash_pin()``).
    """
    CREATE TABLE IF NOT EXISTS teachers (
        id TEXT PRIMARY KEY,
        full_name TEXT NOT NULL,
        pin_hash TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # Мұғалім↔сынып көп-көпке байланысы — ``Classroom``/``Teacher``
    # жазбаларының ӨЗІ ЕШҚАШАН қайталанбайды, тек осы жеке байланыс
    # кестесі арқылы (§ "Do NOT duplicate class records").
    """
    CREATE TABLE IF NOT EXISTS teacher_classroom_assignments (
        teacher_id TEXT NOT NULL,
        classroom_id TEXT NOT NULL,
        PRIMARY KEY (teacher_id, classroom_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_tca_teacher_id ON teacher_classroom_assignments(teacher_id)",
    "CREATE INDEX IF NOT EXISTS idx_tca_classroom_id ON teacher_classroom_assignments(classroom_id)",
    # Жалғыз жол кестесі (``active_student_state``-пен БІРДЕЙ өрнек) —
    # ағымдағы аутентификацияланған мұғалім контексті.
    """
    CREATE TABLE IF NOT EXISTS active_teacher_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        teacher_id TEXT,
        updated_at TEXT NOT NULL
    )
    """,
    # § Offline-First + Cloud Sync Foundation §6 "Local Sync Queue" —
    # durable outbox, қолданба қайта іске қосылса да сақталады. Бір
    # ``(entity_type, entity_sync_id)`` жұбына КӨП ДЕГЕНДЕ БІР күтілетін
    # жазба сәйкес келеді (§7 "Queue Deduplication" — UNIQUE шектеу,
    # жаңа UPSERT ескісін ``INSERT ... ON CONFLICT DO UPDATE`` арқылы
    # АЛМАСТЫРАДЫ, event sourcing ЖОҚ).
    """
    CREATE TABLE IF NOT EXISTS sync_outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL,
        entity_sync_id TEXT NOT NULL,
        operation TEXT NOT NULL,
        created_at TEXT NOT NULL,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        last_error TEXT NOT NULL DEFAULT '',
        next_retry_at TEXT,
        UNIQUE (entity_type, entity_sync_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_sync_outbox_next_retry ON sync_outbox(next_retry_at)",
    # § Phase 4 (Raw Arduino Measurement Cloud Sync): ``measurement_
    # batches`` — ``measurements`` кестесінің ҮСТІНДЕГІ, ЖЕКЕ (parent)
    # метадата кестесі, тек ``sequence_no`` ауқымына СІЛТЕЙДІ (§
    # "prefer a clear parent/child structure" — дерек екі рет
    # көшірілмейді, тек ауқым нұсқалады). ``batch_sync_id`` ӨЗ бетінше
    # UUID (§ ``sync_outbox``-тың ``UNIQUE(entity_type, entity_sync_id)``
    # шектеуі — сессияның ӨЗ sync_id-ін бірнеше batch-қа ортақ
    # entity_sync_id ретінде қолдану МҮМКІН ЕМЕС, әр batch ӨЗ бетінше
    # тәуелсіз push/retry/mark_synced циклін қажет етеді).
    """
    CREATE TABLE IF NOT EXISTS measurement_batches (
        batch_sync_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        sequence_start INTEGER NOT NULL,
        sequence_end INTEGER NOT NULL,
        sample_count INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        sync_state TEXT NOT NULL DEFAULT 'pending_upload',
        server_revision INTEGER,
        FOREIGN KEY(session_id) REFERENCES experiment_sessions(id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_measurement_batches_session_id ON measurement_batches(session_id)",
    # § Phase 7 (Teacher Actions, Feedback Delivery, and Session History):
    # мұғалімнің оқушыға жіберетін қысқа пікірлері — ``experiment_
    # feedback``-тен ӘДЕЙІ БӨЛЕК (§ ол "оқушы жіберген есепті мұғалім
    # бағалайды" ағыны, сессияға БІР жазба; бұл "мұғалім кез келген
    # сәтте қысқа хабар жібереді" ағыны, бір оқушыға КӨП жазба — § "a
    # feed, not a single graded slot", ``domain/entities/teacher_note.py``
    # докстрингі). ``read_at`` ЖЕРГІЛІКТІ-тек, ешқашан синхрондалмайды.
    """
    CREATE TABLE IF NOT EXISTS teacher_notes (
        id TEXT PRIMARY KEY,
        teacher_id TEXT NOT NULL,
        student_id TEXT NOT NULL,
        classroom_id TEXT NOT NULL,
        experiment_id TEXT,
        session_id TEXT,
        message TEXT NOT NULL,
        created_at TEXT NOT NULL,
        read_at TEXT,
        sync_state TEXT NOT NULL DEFAULT 'pending_upload',
        server_revision INTEGER
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_teacher_notes_student ON teacher_notes(student_id, created_at)",
)

# § Phase 4: ``measurements(session_id, sequence_no)`` ЖҰБЫНЫҢ бірегейлігі
# — pull-дан қайта қолданылатын ``INSERT OR IGNORE`` (§ ``apply_remote_
# batch()``) осы индекске сүйенеді (§ "use stable batch identity and
# appropriate DB uniqueness constraints" — тек timestamp-қа сенбеу).
# ЖЕКЕ statement, себебі ЕСКІ (болжам бойынша) деректе қайшы келетін
# қайталама жол болса, идекс құру сәтсіз аяқталуы МҮМКІН — § ``
# initialize_schema()``-дегі граждан қорғаныс (try/except) осыны
# қолданбаны құлатпай өткізеді.
_MEASUREMENT_SEQUENCE_UNIQUE_INDEX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_measurements_session_sequence_unique "
    "ON measurements(session_id, sequence_no)"
)

# § Offline-First + Cloud Sync Foundation §2/§3: КЕМ ЕЛДІК инвазивті
# ALTER TABLE миграция — ЕНДІ БАР үш кестеге (§4 "Do NOT break existing
# database") sync метадата бағандарын қосады. ``(table, column, ddl)``
# үштігі: әр баған ЖЕКЕ, идемпотентті түрде тексеріледі/қосылады.
_ADDITIVE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("teachers", "sync_id", "TEXT NOT NULL DEFAULT ''"),
    ("teachers", "sync_state", "TEXT NOT NULL DEFAULT 'pending_upload'"),
    ("teachers", "server_revision", "INTEGER"),
    ("classrooms", "sync_id", "TEXT NOT NULL DEFAULT ''"),
    ("classrooms", "sync_state", "TEXT NOT NULL DEFAULT 'pending_upload'"),
    ("classrooms", "server_revision", "INTEGER"),
    ("students", "sync_id", "TEXT NOT NULL DEFAULT ''"),
    ("students", "sync_state", "TEXT NOT NULL DEFAULT 'pending_upload'"),
    ("students", "server_revision", "INTEGER"),
    # ``teacher_classroom_assignments``-тың ӨЗІНДЕ ешбір ``id``/``sync_id``
    # ЖОҚ (§ database migration дизайны — байланыс жиыны мұғалімнің
    # ӨЗ sync_id-мен синхрондалады, § domain/services/sync_payload.py),
    # тек incremental pull үшін ``updated_at`` керек.
    ("teacher_classroom_assignments", "updated_at", "TEXT"),
    # § Phase 2 (Experiment Session + Results + Feedback Cloud Sync):
    # ``experiment_sessions.id`` ӘЛДЕҚАШАН UUID (§ audit) — сессияның
    # ӨЗІ entity_sync_id ретінде тікелей қолданылады (Teacher/Classroom/
    # Student-тен айырмашылығы — жеке ``sync_id`` бағаны ҚАЖЕТ ЕМЕС,
    # тек ``sync_state``/``server_revision``). ``updated_at`` бұрын
    # МҮЛДЕ жоқ болатын — pull cursor/incremental sync үшін қосылады.
    ("experiment_sessions", "sync_state", "TEXT NOT NULL DEFAULT 'pending_upload'"),
    ("experiment_sessions", "server_revision", "INTEGER"),
    ("experiment_sessions", "updated_at", "TEXT"),
    # ``session_student_link.session_id`` ӨЗІ entity_sync_id (§ 1:1
    # табиғи кілт, session-мен БІРДЕЙ принцип — жеке sync_id бағаны жоқ).
    ("session_student_link", "sync_state", "TEXT NOT NULL DEFAULT 'pending_upload'"),
    ("session_student_link", "server_revision", "INTEGER"),
    # ``experiment_feedback.session_id`` де entity_sync_id (§ бір
    # session-ге БІР ғана feedback жолы, PRIMARY KEY). Бір физикалық
    # жол ЕКІ тәуелсіз синхрондалатын логикалық entity-ді тасиды
    # (§ "feedback_result" — оқушы авторлық бағандары, "teacher_
    # assessment" — мұғалім бағандары) — сол себепті ЕКІ бөлек sync_
    # state/server_revision жұбы ҚАЖЕТ (§ sqlite_feedback_repository.py
    # докстрингі: екеуі тәуелсіз шақырылады, бірінің жазуы екіншісінің
    # деректерін ЕШҚАШАН жоймайды — sync метадатасы да СОЛ принципті
    # қайталайды).
    ("experiment_feedback", "sync_state", "TEXT NOT NULL DEFAULT 'pending_upload'"),
    ("experiment_feedback", "server_revision", "INTEGER"),
    ("experiment_feedback", "teacher_sync_state", "TEXT NOT NULL DEFAULT 'pending_upload'"),
    ("experiment_feedback", "teacher_server_revision", "INTEGER"),
)


def _add_column_if_missing(connection: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    existing_columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column in existing_columns:
        return
    connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Data Journal кестелерін (жоқ болса) құрады, содан кейін ЕНДІ БАР
    кестелерге қосымша sync бағандарын (жоқ болса) қосады. Бірнеше рет
    шақырылса да қауіпсіз (идемпотентті) — § "Run migration multiple
    times in tests and verify no duplication".
    """
    with connection:
        for statement in _SCHEMA_STATEMENTS:
            connection.execute(statement)
        for table, column, ddl in _ADDITIVE_COLUMNS:
            _add_column_if_missing(connection, table, column, ddl)
        try:
            connection.execute(_MEASUREMENT_SEQUENCE_UNIQUE_INDEX)
        except sqlite3.IntegrityError as exc:
            # § Қорғаныс: ЕСКІ дерекқорда (болжам бойынша) қайшы келетін
            # қайталама (session_id, sequence_no) жол табылса, индекс
            # құру сәтсіз аяқталады — қолданба ЕШҚАШАН құламайды, тек
            # осы жағдайда batch idempotency сол сирек сессиялар үшін
            # DB-деңгейінде күшейтілмейді (§ "must not crash the app").
            _logger.warning(
                "measurements(session_id, sequence_no) UNIQUE индексі құрылмады: %s", exc
            )


def _get_legacy_database_path() -> Path | None:
    """§ Phase 9 (Production Deployment) — Phase 1-8 бойы қолданылған
    ЕСКІ орналасу (``QStandardPaths.AppDataLocation``, Windows-та
    Roaming ``%APPDATA%``). Тек 1 реттік көшіру үшін оқылады, ЕШҚАШАН
    жазылмайды/жойылмайды (§ ``get_default_database_path()`` докстрингі)."""
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    if not base:
        return None
    legacy_path = Path(base) / _DATABASE_FILENAME
    return legacy_path if legacy_path.is_file() else None


def get_default_database_path() -> Path:
    """Пайдаланушының application-data қалтасындағы дефолт DB файл жолын
    қайтарады (Windows-та ``%LOCALAPPDATA%\\ArduinoPhysicsLab\\
    arduino_physics_lab.db``), қалтаны алдын ала жасап қояды.

    ``QStandardPaths.AppLocalDataLocation`` дұрыс нәтиже беруі үшін
    ``QCoreApplication``-да application/organization атауы орнатылған
    болуы керек (``app.py``-де ``run()`` бастапқы кезінде орнатылады).

    § Phase 9 Architecture Decision #2 — Phase 1-8 ``AppDataLocation``
    (Roaming) қолданды; мектеп Windows domain-ындағы roaming profile-мен
    үнемі өсіп отыратын SQLite файлы нашар үйлеседі (баяу
    кіру/шығу синхрондауы, профиль көлемі квотасы), сондықтан ЖАҢА
    орнатулар ``AppLocalDataLocation``-ды (Local, roaming ЕМЕС)
    қолданады. Бар ескі дерекқорлар ЕШҚАШАН жойылмайды/жылжытылмайды —
    жаңа жолда файл ӘЛІ жоқ БОЛСА ғана, ескі жолдан БІР РЕТ, ҚАУІПСІЗ
    КӨШІРІЛЕДІ (move ЕМЕС, copy — § "existing developer databases must
    not be silently destroyed", идемпотентті: 2-ші шақыруда жаңа файл
    әлдеқашан бар болғандықтан ешқандай көшіру қайта орындалмайды).
    """
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    directory = Path(base) if base else Path.home() / ".arduino_physics_lab"
    directory.mkdir(parents=True, exist_ok=True)
    new_path = directory / _DATABASE_FILENAME

    if not new_path.exists():
        legacy_path = _get_legacy_database_path()
        if legacy_path is not None and legacy_path != new_path:
            try:
                shutil.copy2(legacy_path, new_path)
                _logger.info(
                    "Ескі (Roaming) дерекқор жаңа (Local) орналасуға көшірілді: %s -> %s",
                    legacy_path, new_path,
                )
            except OSError as exc:
                _logger.warning("Ескі дерекқорды жаңа орналасуға көшіру сәтсіз аяқталды: %s", exc)

    return new_path
