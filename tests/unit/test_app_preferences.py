"""AppPreferences юнит-тесттері (Phase 22): QSettings-негізді, типтелген
баптау сақтау сервисі — нақты Windows тізіліміне ЕШҚАШАН тимейтін,
уақытша INI файлға негізделген ``QSettings`` данасымен.
"""

import os
import tempfile

import pytest
from PySide6.QtCore import QSettings

from infrastructure.storage.app_preferences import AppPreferences


@pytest.fixture
def temp_settings() -> QSettings:
    handle = tempfile.NamedTemporaryFile(suffix=".ini", delete=False)
    handle.close()
    settings = QSettings(handle.name, QSettings.Format.IniFormat)
    yield settings
    os.unlink(handle.name)


def test_auto_scale_default_is_true_matching_live_graph_current_behavior(temp_settings) -> None:
    """§ "Do NOT silently change the existing default" — LiveGraphWidget-
    тің ӨЗ ескі ``setChecked(True)``-мен БІРДЕЙ."""
    preferences = AppPreferences(temp_settings)
    assert preferences.get_auto_scale_default() is True


def test_set_auto_scale_default_persists() -> None:
    handle = tempfile.NamedTemporaryFile(suffix=".ini", delete=False)
    handle.close()
    try:
        settings = QSettings(handle.name, QSettings.Format.IniFormat)
        AppPreferences(settings).set_auto_scale_default(False)
        settings.sync()

        reloaded_settings = QSettings(handle.name, QSettings.Format.IniFormat)
        assert AppPreferences(reloaded_settings).get_auto_scale_default() is False
    finally:
        os.unlink(handle.name)


def test_reset_to_defaults_restores_auto_scale(temp_settings) -> None:
    preferences = AppPreferences(temp_settings)
    preferences.set_auto_scale_default(False)
    assert preferences.get_auto_scale_default() is False

    preferences.reset_to_defaults()

    assert preferences.get_auto_scale_default() is True


def test_reset_to_defaults_only_touches_own_settings_keys(temp_settings) -> None:
    """§11 "must NOT delete students/classrooms/experiments/results" —
    ``AppPreferences`` домен дерекқорына ЕШБІР қатысы жоқ, тек ӨЗ
    ``QSettings`` данасының кілттерін тазалайды."""
    temp_settings.setValue("unrelated/other_app_key", "should survive")
    preferences = AppPreferences(temp_settings)
    preferences.set_auto_scale_default(False)

    preferences.reset_to_defaults()

    assert temp_settings.value("unrelated/other_app_key") == "should survive"


# ---- Phase 4: measurement batch chunk size ---------------------------------


def test_measurement_batch_chunk_size_default_is_250(temp_settings) -> None:
    preferences = AppPreferences(temp_settings)
    assert preferences.get_measurement_batch_chunk_size() == 250


def test_measurement_batch_chunk_size_persists(temp_settings) -> None:
    preferences = AppPreferences(temp_settings)
    preferences.set_measurement_batch_chunk_size(500)
    assert preferences.get_measurement_batch_chunk_size() == 500


# ---- Phase 5: Connectivity-Aware Automatic Sync intervals -------------------


def test_connectivity_check_interval_default_is_12_seconds(temp_settings) -> None:
    preferences = AppPreferences(temp_settings)
    assert preferences.get_connectivity_check_interval_seconds() == 12


def test_connectivity_check_interval_persists(temp_settings) -> None:
    preferences = AppPreferences(temp_settings)
    preferences.set_connectivity_check_interval_seconds(20)
    assert preferences.get_connectivity_check_interval_seconds() == 20


def test_teacher_auto_refresh_interval_default_is_10_seconds(temp_settings) -> None:
    preferences = AppPreferences(temp_settings)
    assert preferences.get_teacher_auto_refresh_interval_seconds() == 10


def test_teacher_auto_refresh_interval_persists(temp_settings) -> None:
    preferences = AppPreferences(temp_settings)
    preferences.set_teacher_auto_refresh_interval_seconds(15)
    assert preferences.get_teacher_auto_refresh_interval_seconds() == 15


def test_active_experiment_sync_interval_default_is_10_seconds(temp_settings) -> None:
    preferences = AppPreferences(temp_settings)
    assert preferences.get_active_experiment_sync_interval_seconds() == 10


def test_active_experiment_sync_interval_persists(temp_settings) -> None:
    preferences = AppPreferences(temp_settings)
    preferences.set_active_experiment_sync_interval_seconds(5)
    assert preferences.get_active_experiment_sync_interval_seconds() == 5
