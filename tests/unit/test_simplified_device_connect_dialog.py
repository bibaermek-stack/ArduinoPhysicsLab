"""SimplifiedDeviceConnectDialog — юнит-тесттері (Phase 37A).

Бұл диалог ЕШБІР жаңа scan/identify логикасын жасамайды — тек берілген
``DevicePanel`` данасын өз layout-ына уақытша reparent етеді. Тесттер дәл
осы "дубликат жоқ, дайын болғанда автоматты жабылу" кепілдігін тексереді.
"""

import sys

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from ui.widgets.device_panel import DevicePanel
from ui.widgets.simplified_device_connect_dialog import SimplifiedDeviceConnectDialog


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_dialog_reparents_the_given_device_panel_instance() -> None:
    owner = QWidget()
    panel = DevicePanel(owner)
    panel.setVisible(False)

    dialog = SimplifiedDeviceConnectDialog(panel, is_ready=lambda: False)

    assert dialog._device_panel is panel
    assert panel.parent() is dialog
    assert panel.isHidden() is False


def test_closing_dialog_restores_original_parent_and_hides_panel() -> None:
    owner = QWidget()
    panel = DevicePanel(owner)
    panel.setVisible(False)
    dialog = SimplifiedDeviceConnectDialog(panel, is_ready=lambda: False)

    dialog.close()

    assert panel.parent() is owner
    assert panel.isVisible() is False


def test_check_readiness_closes_dialog_when_ready() -> None:
    owner = QWidget()
    panel = DevicePanel(owner)
    is_ready_flag = {"ready": False}
    dialog = SimplifiedDeviceConnectDialog(panel, is_ready=lambda: is_ready_flag["ready"])
    dialog.show()
    assert dialog.isVisible() is True

    is_ready_flag["ready"] = True
    dialog.check_readiness()

    assert dialog.isVisible() is False


def test_check_readiness_keeps_dialog_open_when_not_ready() -> None:
    owner = QWidget()
    panel = DevicePanel(owner)
    dialog = SimplifiedDeviceConnectDialog(panel, is_ready=lambda: False)
    dialog.show()

    dialog.check_readiness()

    assert dialog.isVisible() is True
    dialog.close()


def test_close_button_closes_dialog() -> None:
    owner = QWidget()
    panel = DevicePanel(owner)
    dialog = SimplifiedDeviceConnectDialog(panel, is_ready=lambda: False)
    dialog.show()

    dialog._close_button.click()

    assert dialog.isVisible() is False


def test_no_duplicate_device_panel_created() -> None:
    """Диалог ӨЗ DevicePanel данасын жасамайды — тек берілгенін
    пайдаланады (дубликат scan/identify логикасы ЖОҚ).
    """
    owner = QWidget()
    panel = DevicePanel(owner)

    dialog = SimplifiedDeviceConnectDialog(panel, is_ready=lambda: False)

    panels_in_dialog = dialog.findChildren(DevicePanel)
    assert panels_in_dialog == [panel]
