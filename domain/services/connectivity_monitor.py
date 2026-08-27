"""connectivity_monitor — Phase 5 (Connectivity-Aware Automatic Sync):
"is this client's configured sync server currently reachable" edge
detection, decoupled from the periodic health-check timing itself.

Таза Python — ЕШБІР Qt тәуелділігі жоқ (§ ``domain/services/sync_engine.py``
докстрингіндегі БІРДЕЙ ұстаным: "UI/thread код-ЕМЕС бизнес-логика
таза Python-да, Qt тек жіңішке орауыш"). ``infrastructure/sync/
sync_worker.py`` бұл класты ТЕК ``QTimer.timeout``-та шақырады — нақты
"желіге қашан/қаншалықты жиі тексеру керек" шешімі осында ЕМЕС (§
интервалдың ӨЗІ ``AppPreferences``/``QTimer``-де), тек "СОҢҒЫ екі
тексеру арасында OFFLINE->ONLINE ауысуы болды ма" деген БІР сұраққа
жауап береді.

§ "Do not use generic Internet connectivity such as pinging Google" —
бұл монитор нақты ``ISyncApiClient.check_health()`` (§ "can THIS
client reach ITS configured sync server") нәтижесін алады, ЕШҚАШАН
өзі HTTP жасамайды.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConnectivityCheckResult:
    is_online: bool
    # § "OFFLINE -> ONLINE" ауысуы — §4 "Connectivity-Restored Push
    # Trigger" осы жалғыз өріске тәуелді (§ SyncWorker бұл ``True``
    # болғанда ғана ``run_sync_now()`` шақырады, ӘРБІР тексеруде ЕМЕС).
    just_came_online: bool
    # § "Avoid sync storms": ауысу ЖОҚ уақытта (мыс. тұрақты OFFLINE
    # немесе тұрақты ONLINE) UI-ге ешбір жаңа мән жіберудің қажеті
    # жоқ екенін білдіреді.
    changed: bool


class ConnectivityMonitor:
    """§3 "Automatic Connectivity Monitor": соңғы белгілі күйді
    сақтап, әр ``check()`` шақыруында НАҚТЫ (жаңа) күйді бұрынғысымен
    салыстырады. Бастапқы күй ``None`` ("белгісіз") — БІРІНШІ сәтті
    тексеру ``just_came_online=True`` деп саналады (§ "connectivity
    restored" бастапқы қосылым сәтіне де қолданылады, § app іске
    қосылғаннан кейінгі бірінші sync-пен БІРДЕЙ мағына)."""

    def __init__(self) -> None:
        self._last_known_online: bool | None = None

    @property
    def last_known_online(self) -> bool | None:
        return self._last_known_online

    def check(self, is_online: bool) -> ConnectivityCheckResult:
        """``is_online`` — шақырушы (§ ``SyncWorker``) ӨЗІ жасаған БІР
        ``check_health()``/сәтті sync циклінің нәтижесі. Бұл әдіс ӨЗІ
        ЕШБІР желі әрекетін жасамайды — тек мемлекетті жаңартады."""
        previous = self._last_known_online
        self._last_known_online = is_online
        just_came_online = is_online and previous is not True
        changed = previous != is_online
        return ConnectivityCheckResult(
            is_online=is_online, just_came_online=just_came_online, changed=changed
        )

    def reset(self) -> None:
        """§ тесттерге/диагностикаға арналған — "белгісіз" бастапқы
        күйге қайтарады."""
        self._last_known_online = None
