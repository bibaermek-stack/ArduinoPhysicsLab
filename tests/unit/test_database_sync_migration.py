"""infrastructure/storage/database.py — Offline-First + Cloud Sync
Foundation §4 "Migration must be additive/idempotent/non-destructive"
тесттері.

``initialize_schema()`` екі кезеңнен тұрады: (1) ескі ``CREATE TABLE IF
NOT EXISTS`` DDL (§ бұрыннан бар, sync бағандарынсыз), (2) ЖАҢА
``_add_column_if_missing()`` арқылы аддитивті ``ALTER TABLE``. Бұл
тесттер ЕСКІ (Cloud Sync-тен бұрынғы) дерекқор файлын имитациялау үшін
тек (1)-кезеңді қолмен жүргізіп, содан кейін толық ``initialize_schema()``-
ды шақырады — нақты пайдаланушының бар өндірістік файлын ашумен БІРДЕЙ
жол."""

import sqlite3

from infrastructure.storage.database import (
    _SCHEMA_STATEMENTS,
    initialize_schema,
)


def _create_pre_sync_schema(connection: sqlite3.Connection) -> None:
    """Тек ЕСКІ ``CREATE TABLE`` DDL-ін жүргізеді — sync бағандарынсыз,
    "Cloud Sync фазасынан бұрынғы дерекқор файлы" күйін имитациялайды."""
    with connection:
        for statement in _SCHEMA_STATEMENTS:
            connection.execute(statement)


def test_migration_adds_sync_columns_to_pre_existing_teachers_table() -> None:
    connection = sqlite3.connect(":memory:")
    _create_pre_sync_schema(connection)
    columns_before = {row[1] for row in connection.execute("PRAGMA table_info(teachers)")}
    assert "sync_id" not in columns_before

    initialize_schema(connection)

    columns_after = {row[1] for row in connection.execute("PRAGMA table_info(teachers)")}
    assert {"sync_id", "sync_state", "server_revision"} <= columns_after


def test_migration_preserves_existing_rows_and_defaults_sync_state() -> None:
    connection = sqlite3.connect(":memory:")
    _create_pre_sync_schema(connection)
    with connection:
        connection.execute(
            "INSERT INTO teachers (id, full_name, pin_hash, is_active, created_at, updated_at) "
            "VALUES ('t1', 'Existing Teacher', 'hash', 1, '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00')"
        )

    initialize_schema(connection)

    row = connection.execute(
        "SELECT full_name, pin_hash, sync_id, sync_state FROM teachers WHERE id = 't1'"
    ).fetchone()
    assert row == ("Existing Teacher", "hash", "", "pending_upload")


def test_migration_is_idempotent_when_run_multiple_times() -> None:
    """§4: "test running the migration multiple times to make sure it
    doesn't break anything" — ешбір қате, ешбір қайталанған баған."""
    connection = sqlite3.connect(":memory:")
    _create_pre_sync_schema(connection)

    initialize_schema(connection)
    initialize_schema(connection)
    initialize_schema(connection)

    columns = [row[1] for row in connection.execute("PRAGMA table_info(teachers)")]
    assert columns.count("sync_id") == 1
    assert columns.count("sync_state") == 1
    assert columns.count("server_revision") == 1


def test_fresh_database_gets_sync_outbox_table() -> None:
    connection = sqlite3.connect(":memory:")

    initialize_schema(connection)

    tables = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert "sync_outbox" in tables


def test_migration_adds_teacher_classroom_assignments_updated_at_column() -> None:
    connection = sqlite3.connect(":memory:")
    _create_pre_sync_schema(connection)
    columns_before = {
        row[1] for row in connection.execute("PRAGMA table_info(teacher_classroom_assignments)")
    }
    assert "updated_at" not in columns_before

    initialize_schema(connection)

    columns_after = {
        row[1] for row in connection.execute("PRAGMA table_info(teacher_classroom_assignments)")
    }
    assert "updated_at" in columns_after


# ---- Phase 2 (Experiment Session + Results + Feedback Cloud Sync) --------


def test_migration_adds_session_sync_columns() -> None:
    connection = sqlite3.connect(":memory:")
    _create_pre_sync_schema(connection)
    columns_before = {row[1] for row in connection.execute("PRAGMA table_info(experiment_sessions)")}
    assert "sync_state" not in columns_before

    initialize_schema(connection)

    columns_after = {row[1] for row in connection.execute("PRAGMA table_info(experiment_sessions)")}
    assert {"sync_state", "server_revision", "updated_at"} <= columns_after


def test_migration_adds_session_student_link_sync_columns() -> None:
    connection = sqlite3.connect(":memory:")
    _create_pre_sync_schema(connection)

    initialize_schema(connection)

    columns = {row[1] for row in connection.execute("PRAGMA table_info(session_student_link)")}
    assert {"sync_state", "server_revision"} <= columns


def test_migration_adds_experiment_feedback_sync_columns() -> None:
    connection = sqlite3.connect(":memory:")
    _create_pre_sync_schema(connection)

    initialize_schema(connection)

    columns = {row[1] for row in connection.execute("PRAGMA table_info(experiment_feedback)")}
    assert {"sync_state", "server_revision", "teacher_sync_state", "teacher_server_revision"} <= columns


def test_migration_preserves_existing_session_row_and_defaults_pending_upload() -> None:
    connection = sqlite3.connect(":memory:")
    _create_pre_sync_schema(connection)
    with connection:
        connection.execute(
            "INSERT INTO experiment_sessions "
            "(id, experiment_id, experiment_title, started_at, ended_at, status, "
            "measurement_count, created_at) VALUES "
            "('s1', 'ohms-law', 'Ohm', '2025-01-01T00:00:00+00:00', '2025-01-01T00:05:00+00:00', "
            "'finalized', 10, '2025-01-01T00:00:00+00:00')"
        )

    initialize_schema(connection)

    row = connection.execute(
        "SELECT experiment_title, sync_state FROM experiment_sessions WHERE id = 's1'"
    ).fetchone()
    assert row == ("Ohm", "pending_upload")


def test_phase2_migration_is_idempotent_when_run_multiple_times() -> None:
    connection = sqlite3.connect(":memory:")
    _create_pre_sync_schema(connection)

    initialize_schema(connection)
    initialize_schema(connection)
    initialize_schema(connection)

    columns = [row[1] for row in connection.execute("PRAGMA table_info(experiment_feedback)")]
    assert columns.count("sync_state") == 1
    assert columns.count("teacher_sync_state") == 1
    assert columns.count("teacher_server_revision") == 1
