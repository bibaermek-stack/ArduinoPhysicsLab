"""domain/services/connectivity_monitor.py тесттері — таза Python,
Qt/желі ЖОҚ (§ ConnectivityMonitor докстрингі)."""

from domain.services.connectivity_monitor import ConnectivityMonitor


def test_first_successful_check_is_treated_as_just_came_online() -> None:
    monitor = ConnectivityMonitor()

    result = monitor.check(is_online=True)

    assert result.is_online is True
    assert result.just_came_online is True
    assert result.changed is True


def test_first_failed_check_is_not_a_transition() -> None:
    monitor = ConnectivityMonitor()

    result = monitor.check(is_online=False)

    assert result.is_online is False
    assert result.just_came_online is False
    assert result.changed is True  # § None -> False еш de "connectivity restored" ЕМЕС, БІРАҚ UI-ге хабарлауға тұрарлық


def test_offline_to_online_transition_is_detected() -> None:
    monitor = ConnectivityMonitor()
    monitor.check(is_online=False)

    result = monitor.check(is_online=True)

    assert result.just_came_online is True
    assert result.changed is True


def test_online_to_offline_is_a_change_but_not_just_came_online() -> None:
    monitor = ConnectivityMonitor()
    monitor.check(is_online=True)

    result = monitor.check(is_online=False)

    assert result.is_online is False
    assert result.just_came_online is False
    assert result.changed is True


def test_repeated_online_checks_do_not_flag_repeated_transitions() -> None:
    """§ "Avoid sync storms": тұрақты ONLINE күйде ӘРБІР tick
    ЕШҚАШАН қайта ``just_came_online=True`` қайтармауы керек."""
    monitor = ConnectivityMonitor()
    monitor.check(is_online=True)

    second = monitor.check(is_online=True)
    third = monitor.check(is_online=True)

    assert second.just_came_online is False
    assert second.changed is False
    assert third.just_came_online is False
    assert third.changed is False


def test_repeated_offline_checks_do_not_flag_repeated_changes() -> None:
    monitor = ConnectivityMonitor()
    monitor.check(is_online=False)

    second = monitor.check(is_online=False)

    assert second.changed is False
    assert second.just_came_online is False


def test_flapping_connectivity_each_restore_is_detected() -> None:
    """§ желі "flap" болса (online/offline/online/...) — ӘРБІР ЖАҢА
    online-ға оралу ӨЗІНШЕ ``just_came_online=True`` болуы керек."""
    monitor = ConnectivityMonitor()

    assert monitor.check(is_online=True).just_came_online is True
    assert monitor.check(is_online=False).just_came_online is False
    assert monitor.check(is_online=True).just_came_online is True
    assert monitor.check(is_online=False).just_came_online is False
    assert monitor.check(is_online=True).just_came_online is True


def test_reset_returns_to_unknown_state() -> None:
    monitor = ConnectivityMonitor()
    monitor.check(is_online=True)

    monitor.reset()

    assert monitor.last_known_online is None
    assert monitor.check(is_online=True).just_came_online is True


def test_last_known_online_property_reflects_most_recent_check() -> None:
    monitor = ConnectivityMonitor()
    assert monitor.last_known_online is None

    monitor.check(is_online=False)
    assert monitor.last_known_online is False

    monitor.check(is_online=True)
    assert monitor.last_known_online is True
