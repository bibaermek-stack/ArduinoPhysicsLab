import sys

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_second_lock_fails(monkeypatch) -> None:
    from infrastructure.os.single_instance import SingleInstance
    a = SingleInstance(name="apl-test-lock")
    b = SingleInstance(name="apl-test-lock")
    assert a.try_lock() is True
    assert b.try_lock() is False
    a.close()


def test_close_releases_lock() -> None:
    from infrastructure.os.single_instance import SingleInstance

    a = SingleInstance(name="apl-test-lock-close")
    b = SingleInstance(name="apl-test-lock-close")
    assert a.try_lock() is True
    a.close()
    assert b.try_lock() is True
    b.close()


def test_send_raise_invokes_on_raise(qt_application: QApplication) -> None:
    from infrastructure.os.single_instance import SingleInstance

    raised: list[int] = []
    owner = SingleInstance(name="apl-test-lock-raise")
    peer = SingleInstance(name="apl-test-lock-raise")
    assert owner.try_lock() is True
    owner.on_raise(lambda: raised.append(1))
    peer.send_raise()
    qt_application.processEvents()
    assert raised == [1]
    owner.close()
    peer.close()


class _Window:
    def __init__(self, visible: bool = True) -> None:
        self._visible = visible

    def isVisible(self) -> bool:
        return self._visible

    def close(self) -> None:
        self._visible = False


def test_window_to_raise_skips_closed_cloud_picker() -> None:
    from infrastructure.os.single_instance import window_to_raise

    auth = _Window(True)
    picker = _Window(True)
    role = _Window(False)
    picker.close()
    assert window_to_raise([], [picker], role, auth) is auth


def test_window_to_raise_prefers_main_then_visible_picker() -> None:
    from infrastructure.os.single_instance import window_to_raise

    main = _Window()
    picker = _Window()
    role = _Window()
    auth = _Window()
    assert window_to_raise([main], [picker], role, auth) is main
    assert window_to_raise([], [picker], role, auth) is picker
    picker.close()
    assert window_to_raise([], [picker], role, auth) is role
    role.close()
    assert window_to_raise([], [picker], role, auth) is auth
