"""core/deployment_config.py және соған тәуелді әдепкі sync баптаулары."""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from core.deployment_config import load_deployment_config
from domain.services.sync_auth import get_configured_sync_api_key
from infrastructure.storage.app_preferences import AppPreferences
from infrastructure.sync.http_sync_api_client import HttpSyncApiClient


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def isolated_deployment(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.delenv("APL_DEPLOYMENT_CONFIG", raising=False)
    monkeypatch.delenv("APL_SYNC_API_KEY", raising=False)
    config_path = tmp_path / "deployment.json"
    monkeypatch.setenv("APL_DEPLOYMENT_CONFIG", str(config_path))
    return config_path


@pytest.fixture
def temp_preferences():
    handle = tempfile.NamedTemporaryFile(suffix=".ini", delete=False)
    handle.close()
    settings = QSettings(handle.name, QSettings.Format.IniFormat)
    yield AppPreferences(settings)
    os.unlink(handle.name)


def test_missing_file_returns_empty_config(isolated_deployment) -> None:
    config = load_deployment_config()
    assert config.sync_api_base_url == ""
    assert config.sync_enabled is None
    assert config.sync_api_key == ""


def test_valid_deployment_file_is_loaded(isolated_deployment) -> None:
    isolated_deployment.write_text(
        json.dumps(
            {
                "sync_api_base_url": "https://lab.example.kz",
                "sync_enabled": True,
                "sync_api_key": "school-key",
            }
        ),
        encoding="utf-8",
    )

    config = load_deployment_config()
    assert config.sync_api_base_url == "https://lab.example.kz"
    assert config.sync_enabled is True
    assert config.sync_api_key == "school-key"


def test_broken_json_is_ignored(isolated_deployment) -> None:
    isolated_deployment.write_text("{not json", encoding="utf-8")
    config = load_deployment_config()
    assert config.sync_api_base_url == ""


def test_preferences_use_deployment_url_when_unset(isolated_deployment, temp_preferences) -> None:
    isolated_deployment.write_text(
        json.dumps({"sync_api_base_url": "https://lab.example.kz", "sync_enabled": True}),
        encoding="utf-8",
    )

    assert temp_preferences.get_sync_api_base_url() == "https://lab.example.kz"
    assert temp_preferences.get_sync_enabled() is True


def test_saved_preferences_override_deployment(isolated_deployment, temp_preferences) -> None:
    isolated_deployment.write_text(
        json.dumps({"sync_api_base_url": "https://lab.example.kz", "sync_enabled": True}),
        encoding="utf-8",
    )
    temp_preferences.set_sync_api_base_url("https://other.example.kz")
    temp_preferences.set_sync_enabled(False)

    assert temp_preferences.get_sync_api_base_url() == "https://other.example.kz"
    assert temp_preferences.get_sync_enabled() is False


def test_reset_falls_back_to_deployment(isolated_deployment, temp_preferences) -> None:
    isolated_deployment.write_text(
        json.dumps({"sync_api_base_url": "https://lab.example.kz", "sync_enabled": True}),
        encoding="utf-8",
    )
    temp_preferences.set_sync_api_base_url("https://other.example.kz")
    temp_preferences.set_sync_enabled(False)
    temp_preferences.reset_to_defaults()

    assert temp_preferences.get_sync_api_base_url() == "https://lab.example.kz"
    assert temp_preferences.get_sync_enabled() is True


def test_api_key_prefers_env_over_deployment(isolated_deployment, monkeypatch: pytest.MonkeyPatch) -> None:
    isolated_deployment.write_text(json.dumps({"sync_api_key": "from-file"}), encoding="utf-8")
    monkeypatch.setenv("APL_SYNC_API_KEY", "from-env")
    assert get_configured_sync_api_key() == "from-env"


def test_api_key_uses_deployment_when_env_missing(isolated_deployment) -> None:
    isolated_deployment.write_text(json.dumps({"sync_api_key": "from-file"}), encoding="utf-8")
    assert get_configured_sync_api_key() == "from-file"


def test_http_client_configure_updates_base_url() -> None:
    client = HttpSyncApiClient(base_url="http://127.0.0.1:8000", api_key="old")
    client.configure(base_url="https://lab.example.kz", api_key="new", request_timeout=9.0)
    assert client._base_url == "https://lab.example.kz"
    assert client._api_key == "new"
    assert client._request_timeout == 9.0
