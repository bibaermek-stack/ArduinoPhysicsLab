"""sync_backoff — §17 "Retry Strategy": шектелген, қарапайым қайталау
кестесі (1/5/15/30 мин, содан кейін 30 мин-та тұрақталады).

Экспоненциалды емес, БЕКІТІЛГЕН баспалдақ — "do not overcomplicate"
принципіне сай, толық jitter/экспоненциалды формула бұл фаза үшін
артық.
"""

from __future__ import annotations

from datetime import datetime, timedelta

_SCHEDULE_MINUTES: tuple[int, ...] = (1, 5, 15, 30)


def compute_next_retry_at(attempt_count: int, now: datetime) -> datetime:
    """``attempt_count`` — осы әрекетке ДЕЙІНГІ сәтсіз әрекеттер саны
    (0-ден бастап). Кестеден асып кетсе, ЕҢ СОҢҒЫ (30 мин) аралықта
    тұрақталады (§ "do not retry every second")."""
    index = min(attempt_count, len(_SCHEDULE_MINUTES) - 1)
    return now + timedelta(minutes=_SCHEDULE_MINUTES[index])
