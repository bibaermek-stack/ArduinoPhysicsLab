"""Classroom/Student/Teacher репозиторийлерінің ``sync_outbox_
repository``-мен байланысы (§6/§7/§18 — жазу әдістері дұрыс OutboxEntry
кезектейді, remote apply/mark_synced әдістері ЕШБІР outbox жазуын
ЖАСАМАЙДЫ, network-тің болмауы жергілікті жазуды бөгемейді)."""

from datetime import datetime, timezone

from domain.entities.classroom import Classroom
from domain.entities.outbox_entry import OutboxOperation
from domain.entities.student import Student
from domain.entities.sync_state import SyncState
from domain.entities.teacher import Teacher
from domain.entities.user_role import UserRole
from domain.services.teacher_pin import hash_pin
from infrastructure.storage.sqlite_classroom_repository import SqliteClassroomRepository
from infrastructure.storage.sqlite_student_repository import SqliteStudentRepository
from infrastructure.storage.sqlite_sync_outbox_repository import SqliteSyncOutboxRepository
from infrastructure.storage.sqlite_teacher_repository import SqliteTeacherRepository

_NOW = datetime.now(timezone.utc)


# ---- Outbox параметрі берілмесе, ешбір жазба жасалмайды -------------------


def test_classroom_repository_without_outbox_never_enqueues() -> None:
    """§ "500+ existing tests remain unaffected" — outbox параметрі
    ЕРІКТІ, берілмесе жергілікті жазу ЕШБІР жаңа әрекет тудырмайды
    (сынау мақсаты: жаңа код ЕШБІР exception лақтырмайды)."""
    repo = SqliteClassroomRepository()
    repo.create(Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    assert repo.get("c1") is not None


# ---- create()/update()/archive() дұрыс OutboxOperation кезектейді ---------


def test_classroom_create_enqueues_upsert() -> None:
    outbox = SqliteSyncOutboxRepository()
    repo = SqliteClassroomRepository(sync_outbox_repository=outbox)

    repo.create(Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)

    entries = outbox.list_all()
    assert len(entries) == 1
    assert entries[0].entity_type == "classroom"
    assert entries[0].entity_sync_id == "c1"
    assert entries[0].operation is OutboxOperation.UPSERT


def test_classroom_multiple_edits_coalesce_to_one_outbox_entry() -> None:
    """§7: бірнеше кезекті офлайн өзгеріс -> БІР ғана тиімді push."""
    outbox = SqliteSyncOutboxRepository()
    repo = SqliteClassroomRepository(sync_outbox_repository=outbox)
    repo.create(Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)

    for name in ("8Ә", "8Б", "8В"):
        repo.update(
            Classroom(id="c1", name=name, created_at=_NOW, updated_at=_NOW, sync_id="c1"),
            UserRole.TEACHER,
        )

    assert outbox.count_pending() == 1


def test_classroom_archive_enqueues_delete_operation() -> None:
    outbox = SqliteSyncOutboxRepository()
    repo = SqliteClassroomRepository(sync_outbox_repository=outbox)
    repo.create(Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)

    repo.archive("c1", UserRole.TEACHER, archived=True)

    entries = outbox.list_all()
    assert entries[-1].operation is OutboxOperation.DELETE


def test_classroom_unarchive_enqueues_upsert_operation() -> None:
    outbox = SqliteSyncOutboxRepository()
    repo = SqliteClassroomRepository(sync_outbox_repository=outbox)
    repo.create(Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    repo.archive("c1", UserRole.TEACHER, archived=True)

    repo.archive("c1", UserRole.TEACHER, archived=False)

    entries = outbox.list_all()
    assert entries[-1].operation is OutboxOperation.UPSERT


def test_student_create_enqueues_upsert() -> None:
    outbox = SqliteSyncOutboxRepository()
    repo = SqliteStudentRepository(sync_outbox_repository=outbox)

    repo.create(
        Student(id="s1", classroom_id="c1", first_name="A", last_name="B", created_at=_NOW, updated_at=_NOW),
        UserRole.TEACHER,
    )

    entries = outbox.list_all()
    assert entries[0].entity_type == "student"
    assert entries[0].entity_sync_id == "s1"


def test_teacher_create_enqueues_teacher_and_teacher_classroom() -> None:
    """§ ``SqliteTeacherRepository.create()`` — ``set_assigned_classroom_
    ids()`` арқылы, тағайындау бос болса да, teacher_classroom entity_type
    кезектеледі (тіпті бос жиынмен де серверге хабарлануы тиіс)."""
    outbox = SqliteSyncOutboxRepository()
    repo = SqliteTeacherRepository(sync_outbox_repository=outbox)

    repo.create(
        Teacher(id="t1", full_name="X", pin_hash=hash_pin("1234"), created_at=_NOW, updated_at=_NOW),
        assigned_classroom_ids=("c1",),
    )

    entity_types = {entry.entity_type for entry in outbox.list_all()}
    assert entity_types == {"teacher", "teacher_classroom"}


# ---- Remote apply/mark_synced ЕШБІР outbox жазуын жасамайды ---------------


def test_apply_remote_upsert_does_not_enqueue_outbox_entry() -> None:
    """§18 "Pull Sync": pull-дан алынған дерек серверге ҚАЙТА
    жіберілмеуі керек, әйтпесе шексіз push<->pull циклі туар еді."""
    outbox = SqliteSyncOutboxRepository()
    repo = SqliteClassroomRepository(sync_outbox_repository=outbox)

    repo.apply_remote_upsert(
        Classroom(
            id="c1", name="Remote 8А", created_at=_NOW, updated_at=_NOW,
            sync_id="c1", sync_state=SyncState.SYNCED, server_revision=1,
        )
    )

    assert outbox.count_pending() == 0
    stored = repo.get("c1")
    assert stored is not None
    assert stored.sync_state is SyncState.SYNCED


def test_mark_synced_does_not_enqueue_outbox_entry() -> None:
    outbox = SqliteSyncOutboxRepository()
    repo = SqliteClassroomRepository(sync_outbox_repository=outbox)
    repo.create(Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)
    outbox.mark_success(outbox.list_all()[0].id)

    repo.mark_synced("c1", server_revision=1)

    assert outbox.count_pending() == 0
    assert repo.get("c1").sync_state is SyncState.SYNCED


def test_local_write_succeeds_even_though_no_network_is_involved() -> None:
    """§5 "Local-First Writes": жаңа жазба сервер жауабын КҮТПЕЙДІ —
    репозиторий деңгейінде желі ұғымының ӨЗІ жоқ, сондықтан жазу
    ӘРҚАШАН жедел (§ ``SyncEngine`` ҒАНА HTTP қолданады, репозиторий
    ЕШҚАШАН қолданбайды)."""
    outbox = SqliteSyncOutboxRepository()
    repo = SqliteClassroomRepository(sync_outbox_repository=outbox)

    repo.create(Classroom(id="c1", name="8А", created_at=_NOW, updated_at=_NOW), UserRole.TEACHER)

    assert repo.get("c1") is not None
    assert outbox.count_pending() == 1
