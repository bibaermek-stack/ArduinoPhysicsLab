"""``infrastructure/storage/database.py`` — DB орналасуы + Roaming→Local
көшіру миграциясының юнит-тесттері (Phase 9 — Production Deployment &
Release Readiness, § Architecture Decision #2).

``QStandardPaths.writableLocation()`` monkeypatch арқылы ``tmp_path``
ішіндегі жалған "Roaming"/"Local" қалталарға бағытталады — НАҚТЫ
``%APPDATA%``/``%LOCALAPPDATA%``-ге ЕШҚАШАН жазбайды/оқымайды (§ "Do
not write brittle tests tied to the developer's real machine state").
"""

from pathlib import Path

from PySide6.QtCore import QStandardPaths

import infrastructure.storage.database as database_module
from infrastructure.storage.database import get_default_database_path


def _patch_locations(monkeypatch, tmp_path: Path, *, roaming: Path, local: Path) -> None:
    def fake_writable_location(location: QStandardPaths.StandardLocation) -> str:
        if location == QStandardPaths.StandardLocation.AppDataLocation:
            return str(roaming)
        if location == QStandardPaths.StandardLocation.AppLocalDataLocation:
            return str(local)
        return str(tmp_path)

    monkeypatch.setattr(
        database_module.QStandardPaths, "writableLocation", staticmethod(fake_writable_location)
    )


def test_new_installs_use_local_not_roaming(monkeypatch, tmp_path: Path) -> None:
    """§ Architecture Decision #2 — ЖАҢА орнатулар ``AppLocalDataLocation``
    (Local) қолданады, ЕШҚАШАН ``AppDataLocation`` (Roaming) ЕМЕС."""
    roaming = tmp_path / "roaming"
    local = tmp_path / "local"
    _patch_locations(monkeypatch, tmp_path, roaming=roaming, local=local)

    db_path = get_default_database_path()

    assert db_path.parent == local
    assert local.is_dir()


def test_legacy_roaming_database_is_copied_not_moved(monkeypatch, tmp_path: Path) -> None:
    """§ "existing developer databases must not be silently destroyed" —
    ескі (Roaming) файл БАР, жаңа (Local) файл ЖОҚ болса, БІР реттік
    КӨШІРУ (move ЕМЕС) орындалады — ескі файл сақталады."""
    roaming = tmp_path / "roaming"
    local = tmp_path / "local"
    roaming.mkdir(parents=True)
    legacy_db = roaming / "arduino_physics_lab.db"
    legacy_db.write_bytes(b"legacy-database-content")
    _patch_locations(monkeypatch, tmp_path, roaming=roaming, local=local)

    new_path = get_default_database_path()

    assert new_path.exists()
    assert new_path.read_bytes() == b"legacy-database-content"
    # § move ЕМЕС — ескі файл ӘЛІ де бар, мазмұны өзгермеген.
    assert legacy_db.exists()
    assert legacy_db.read_bytes() == b"legacy-database-content"


def test_migration_is_idempotent_and_never_overwrites_newer_local_data(
    monkeypatch, tmp_path: Path
) -> None:
    """§ "idempotent, additive" — жаңа (Local) файл ӘЛДЕҚАШАН бар болса
    (мыс. екінші шақыру, немесе пайдаланушы Local файлды қолдана
    бастаған), ескі (Roaming) файл ЕШҚАШАН оны үстінен жазбайды."""
    roaming = tmp_path / "roaming"
    local = tmp_path / "local"
    roaming.mkdir(parents=True)
    (roaming / "arduino_physics_lab.db").write_bytes(b"OLD-legacy-content")
    local.mkdir(parents=True)
    (local / "arduino_physics_lab.db").write_bytes(b"NEWER-local-content")
    _patch_locations(monkeypatch, tmp_path, roaming=roaming, local=local)

    new_path = get_default_database_path()

    assert new_path.read_bytes() == b"NEWER-local-content"

    # Екінші шақыру — толығымен идемпотентті.
    second_call_path = get_default_database_path()
    assert second_call_path.read_bytes() == b"NEWER-local-content"


def test_no_legacy_database_means_no_copy_attempted(monkeypatch, tmp_path: Path) -> None:
    """§ "clean install" жағдайы — Roaming қалтасында ешбір ескі файл
    жоқ болса, жаңа орнату қарапайым бос Local қалтадан бастайды,
    ешбір exception шықпайды."""
    roaming = tmp_path / "roaming"
    local = tmp_path / "local"
    _patch_locations(monkeypatch, tmp_path, roaming=roaming, local=local)

    new_path = get_default_database_path()

    assert not new_path.exists()
    assert new_path.parent == local
