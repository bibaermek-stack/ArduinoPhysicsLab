"""ChannelAggregator үшін юнит-тесттер."""

from domain.services.channel_aggregator import ChannelAggregator


def test_single_expected_channel_returns_snapshot_immediately() -> None:
    aggregator = ChannelAggregator(expected_channels=frozenset({"voltage"}))

    result = aggregator.update("voltage", 5.024, timestamp=0.0)

    assert result == {"voltage": 5.024}


def test_incomplete_update_returns_none() -> None:
    aggregator = ChannelAggregator(expected_channels=frozenset({"voltage", "current"}))

    result = aggregator.update("voltage", 5.024, timestamp=0.0)

    assert result is None


def test_second_channel_completes_snapshot() -> None:
    aggregator = ChannelAggregator(expected_channels=frozenset({"voltage", "current"}))
    aggregator.update("voltage", 5.024, timestamp=0.0)

    result = aggregator.update("current", 0.218, timestamp=0.04)

    assert result == {"voltage": 5.024, "current": 0.218}


def test_stale_channel_is_not_included_in_snapshot() -> None:
    aggregator = ChannelAggregator(
        expected_channels=frozenset({"voltage", "current"}), staleness_seconds=0.5
    )
    aggregator.update("voltage", 5.024, timestamp=0.0)

    # current 0.6с кейін келеді — voltage сол кезде 0.6с "ескі" болады (>0.5с шегі).
    result = aggregator.update("current", 0.218, timestamp=0.6)

    assert result is None


def test_fresh_update_after_stale_period_completes_snapshot() -> None:
    aggregator = ChannelAggregator(
        expected_channels=frozenset({"voltage", "current"}), staleness_seconds=0.5
    )
    aggregator.update("voltage", 5.024, timestamp=0.0)
    aggregator.update("current", 0.218, timestamp=0.6)  # stale, None қайтарды

    # voltage қайта жаңарды — енді екеуі де fresh.
    result = aggregator.update("voltage", 5.05, timestamp=0.7)

    assert result == {"voltage": 5.05, "current": 0.218}


def test_unexpected_channel_key_is_ignored() -> None:
    aggregator = ChannelAggregator(expected_channels=frozenset({"voltage"}))

    result = aggregator.update("temperature", 24.5, timestamp=0.0)

    assert result is None


def test_multiple_updates_of_same_channel_use_latest_value() -> None:
    aggregator = ChannelAggregator(expected_channels=frozenset({"voltage"}))
    aggregator.update("voltage", 1.0, timestamp=0.0)

    result = aggregator.update("voltage", 2.0, timestamp=0.1)

    assert result == {"voltage": 2.0}


def test_missing_channels_reports_never_received() -> None:
    aggregator = ChannelAggregator(expected_channels=frozenset({"voltage", "current"}))
    # timestamp әдейі берілмейді — missing_channels() те нақты time.monotonic()
    # қолданатындықтан, voltage жаңа ғана келгендіктен "жоқ" деп саналмауы керек.
    aggregator.update("voltage", 5.024)

    assert aggregator.missing_channels() == {"current"}


def test_missing_channels_empty_when_all_fresh() -> None:
    aggregator = ChannelAggregator(expected_channels=frozenset({"voltage", "current"}))
    aggregator.update("voltage", 5.024)
    aggregator.update("current", 0.218)

    assert aggregator.missing_channels() == frozenset()


def test_reset_clears_cached_values() -> None:
    aggregator = ChannelAggregator(expected_channels=frozenset({"voltage", "current"}))
    aggregator.update("voltage", 5.024, timestamp=0.0)
    aggregator.update("current", 0.218, timestamp=0.0)

    aggregator.reset()

    assert aggregator.update("voltage", 5.024, timestamp=1.0) is None
    assert aggregator.missing_channels() == {"voltage", "current"}


def test_empty_expected_channels_never_returns_snapshot() -> None:
    aggregator = ChannelAggregator(expected_channels=frozenset())

    result = aggregator.update("voltage", 5.024, timestamp=0.0)

    assert result is None


def test_update_uses_real_monotonic_time_when_timestamp_omitted() -> None:
    aggregator = ChannelAggregator(expected_channels=frozenset({"voltage"}))

    result = aggregator.update("voltage", 5.024)

    assert result == {"voltage": 5.024}
