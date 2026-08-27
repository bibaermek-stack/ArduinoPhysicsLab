"""server.app.main — Phase 9 (Production Deployment) startup-warning
юнит-тесттері (§ Part J "Server production configuration").

Ескерту тек ЛОГҚА жазылады (§ "not a hard failure") — сервер іске
қосылуын ешқашан бұғаттамайды. Тестер ортаны нақты ``monkeypatch.
delenv``/``setenv`` арқылы басқарады, нақты ортаны ЕШҚАШАН өзгертпейді.
"""

import logging

import pytest

from server.app.main import _warn_if_using_dev_default_secrets


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APL_JWT_SECRET", raising=False)
    monkeypatch.delenv("APL_SYNC_API_KEY", raising=False)


def test_warns_when_both_env_vars_unset(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="server.app.main"):
        _warn_if_using_dev_default_secrets()

    messages = [record.message for record in caplog.records]
    assert any("APL_JWT_SECRET" in message for message in messages)
    assert any("APL_SYNC_API_KEY" in message for message in messages)


def test_no_warning_when_both_env_vars_set(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("APL_JWT_SECRET", "a-real-production-secret-value-1234567890")
    monkeypatch.setenv("APL_SYNC_API_KEY", "a-real-production-api-key")

    with caplog.at_level(logging.WARNING, logger="server.app.main"):
        _warn_if_using_dev_default_secrets()

    assert caplog.records == []


def test_warns_only_for_the_unset_one(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("APL_JWT_SECRET", "a-real-production-secret-value-1234567890")
    # APL_SYNC_API_KEY intentionally left unset.

    with caplog.at_level(logging.WARNING, logger="server.app.main"):
        _warn_if_using_dev_default_secrets()

    messages = [record.message for record in caplog.records]
    assert not any("APL_JWT_SECRET" in message for message in messages)
    assert any("APL_SYNC_API_KEY" in message for message in messages)


def test_warning_never_includes_the_actual_secret_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """§ "But NEVER log: ... secrets" — ескерту хабары ТЕК env айнымалы
    атын атайды, ешбір нақты мән (dev-placeholder болса да) логталмайды."""
    with caplog.at_level(logging.WARNING, logger="server.app.main"):
        _warn_if_using_dev_default_secrets()

    for record in caplog.records:
        assert "dev-local-only" not in record.message
