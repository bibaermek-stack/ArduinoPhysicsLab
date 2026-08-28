"""login_rate_limiter — teacher/student login брутфорс қорғанысы.

5 сәтсіз әрекет → 5 минут құлып. Күй PostgreSQL/SQLite-те сақталады,
сондықтан бірнеше сервер инстансы құлыпты бөліседі.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from server.app.models.sync_models import LoginLockoutRecord

_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 300.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def is_locked(db: Session, identity: str) -> bool:
    row = db.get(LoginLockoutRecord, identity)
    if row is None or row.locked_until is None:
        return False
    locked_until = _aware(row.locked_until)
    if locked_until is not None and locked_until <= _utcnow():
        db.delete(row)
        db.flush()
        return False
    return True


def record_failure(db: Session, identity: str) -> None:
    now = _utcnow()
    row = db.get(LoginLockoutRecord, identity)
    if row is None:
        row = LoginLockoutRecord(
            identity=identity,
            failed_count=0,
            first_failed_at=now,
            locked_until=None,
        )
        db.add(row)
    window_start = now - timedelta(seconds=_LOCKOUT_SECONDS)
    first_failed = _aware(row.first_failed_at) or now
    locked_until = _aware(row.locked_until)
    if first_failed < window_start and (locked_until is None or locked_until <= now):
        row.failed_count = 0
        row.first_failed_at = now
        row.locked_until = None
    row.failed_count += 1
    if row.failed_count >= _MAX_ATTEMPTS:
        row.locked_until = now + timedelta(seconds=_LOCKOUT_SECONDS)
    db.flush()


def record_success(db: Session, identity: str) -> None:
    row = db.get(LoginLockoutRecord, identity)
    if row is not None:
        db.delete(row)
        db.flush()


def reset_all() -> None:
    """Тесттерде дерекқор әр жолы жаңа — қосымша тазалау қажет емес."""
    return
