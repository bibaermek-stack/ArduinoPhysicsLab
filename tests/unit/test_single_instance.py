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
