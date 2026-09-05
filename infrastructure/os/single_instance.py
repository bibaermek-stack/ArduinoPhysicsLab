"""Named local-socket lock so a second process raises the first window.

``QLocalServer.listen()`` is not exclusive on Windows with this Qt build
(two servers can listen on the same pipe name). The lock is a
``QSharedMemory`` segment keyed by the same name; ``QLocalServer`` is
used to deliver ``send_raise()``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from PySide6.QtCore import QSharedMemory
from PySide6.QtNetwork import QLocalServer, QLocalSocket

_RAISE_TIMEOUT_MS = 1000


def window_to_raise(
    main_windows: Sequence[Any],
    cloud_role_pages: Sequence[Any],
    role_selection_page: Any,
    account_auth_page: Any,
) -> Any:
    """Pick the window a second launch should surface.

    Closed cloud role pickers are ignored so a stale picker cannot cover
    login or fire leftover role-selected slots.
    """
    if main_windows:
        return main_windows[-1]
    for page in reversed(cloud_role_pages):
        if page.isVisible():
            return page
    if role_selection_page is not None and role_selection_page.isVisible():
        return role_selection_page
    return account_auth_page


class SingleInstance:
    def __init__(self, name: str) -> None:
        self._name = name
        self._memory = QSharedMemory(name)
        self._server = QLocalServer()
        self._raise_callback: Callable[[], None] | None = None
        self._owns_lock = False
        self._server.newConnection.connect(self._on_new_connection)

    def try_lock(self) -> bool:
        if not self._memory.create(1):
            return False
        QLocalServer.removeServer(self._name)
        if not self._server.listen(self._name):
            self._memory.detach()
            return False
        self._owns_lock = True
        return True

    def send_raise(self) -> None:
        socket = QLocalSocket()
        socket.connectToServer(self._name)
        if not socket.waitForConnected(_RAISE_TIMEOUT_MS):
            socket.close()
            return
        socket.write(b"raise")
        socket.flush()
        socket.waitForBytesWritten(100)
        socket.abort()

    def on_raise(self, callback: Callable[[], None]) -> None:
        self._raise_callback = callback

    def close(self) -> None:
        try:
            self._server.newConnection.disconnect(self._on_new_connection)
        except (TypeError, RuntimeError):
            pass
        self._server.close()
        if self._owns_lock:
            QLocalServer.removeServer(self._name)
        if self._memory.isAttached():
            self._memory.detach()
        self._owns_lock = False

    def _on_new_connection(self) -> None:
        connection = self._server.nextPendingConnection()
        if connection is not None:
            connection.readyRead.connect(connection.readAll)
            connection.disconnected.connect(connection.deleteLater)
        if self._raise_callback is not None:
            self._raise_callback()
