"""domain/services/sync_backoff.py тесттері (§17 "Retry Strategy")."""

from datetime import datetime, timedelta, timezone

from domain.services.sync_backoff import compute_next_retry_at


def test_first_attempt_retries_after_one_minute() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert compute_next_retry_at(0, now) == now + timedelta(minutes=1)


def test_schedule_progresses_through_fixed_steps() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert compute_next_retry_at(1, now) == now + timedelta(minutes=5)
    assert compute_next_retry_at(2, now) == now + timedelta(minutes=15)
    assert compute_next_retry_at(3, now) == now + timedelta(minutes=30)


def test_schedule_caps_at_final_step_for_many_attempts() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert compute_next_retry_at(10, now) == now + timedelta(minutes=30)
    assert compute_next_retry_at(1000, now) == now + timedelta(minutes=30)
