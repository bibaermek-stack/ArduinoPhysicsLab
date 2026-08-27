"""teacher_pin — Мұғалім PIN хэштеу/тексеру қызметінің юнит-тесттері
(Phase 37A).
"""

import os

import pytest

from domain.services.teacher_pin import get_configured_pin_hash, hash_pin, verify_pin


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APL_TEACHER_PIN", raising=False)


def test_hash_pin_is_not_the_plaintext() -> None:
    assert hash_pin("1234") != "1234"


def test_hash_pin_is_deterministic() -> None:
    assert hash_pin("1234") == hash_pin("1234")


def test_hash_pin_differs_for_different_pins() -> None:
    assert hash_pin("1234") != hash_pin("4321")


def test_default_dev_pin_is_1234() -> None:
    expected_hash = get_configured_pin_hash()
    assert verify_pin("1234", expected_hash) is True


def test_wrong_pin_is_rejected() -> None:
    expected_hash = get_configured_pin_hash()
    assert verify_pin("0000", expected_hash) is False


def test_env_var_overrides_default_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APL_TEACHER_PIN", "9999")

    expected_hash = get_configured_pin_hash()

    assert verify_pin("9999", expected_hash) is True
    assert verify_pin("1234", expected_hash) is False


def test_get_configured_pin_hash_never_returns_plaintext(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APL_TEACHER_PIN", "5678")

    result = get_configured_pin_hash()

    assert "5678" not in result
    assert result == hash_pin("5678")
