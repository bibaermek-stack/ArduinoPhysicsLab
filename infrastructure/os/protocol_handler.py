"""Windows ``arduinolab://`` protocol registration (HKCU, no admin).

Tests inject ``set_value`` and never touch the real registry. ``app.py``
calls ``register_protocol`` only when ``sys.frozen`` so pytest does not
write HKCU.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

PROTOCOL_SCHEME = "arduinolab"
_OPEN_URL = f"{PROTOCOL_SCHEME}://open"


def command_for(exe_path: str) -> str:
    return f'"{exe_path}" "%1"'


def is_open_url(arg: str) -> bool:
    return arg == _OPEN_URL or arg == f"{_OPEN_URL}/"


def _default_set_value(scheme: str, command: str) -> None:
    if sys.platform != "win32":
        return
    import winreg

    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{scheme}")
    try:
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ, "URL:Arduino Physics Lab")
        winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
        cmd = winreg.CreateKey(key, r"shell\open\command")
        try:
            winreg.SetValueEx(cmd, None, 0, winreg.REG_SZ, command)
        finally:
            cmd.Close()
    finally:
        key.Close()


def register_protocol(
    exe_path: str,
    *,
    set_value: Callable[[str, str], None] | None = None,
) -> None:
    writer = _default_set_value if set_value is None else set_value
    writer(PROTOCOL_SCHEME, command_for(exe_path))
