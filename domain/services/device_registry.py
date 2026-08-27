"""DeviceRegistry — анықталған (ConnectedDevice) құрылғыларды port_name
және device_id бойынша сақтайтын domain сервисі.
"""

from domain.entities.connected_device import ConnectedDevice


class DeviceRegistry:
    """Анықталған құрылғыларды port_name/device_id бойынша сақтайтын,
    жады ішіндегі (in-memory) тіркеу сервисі.
    """

    def __init__(self) -> None:
        self._by_port: dict[str, ConnectedDevice] = {}
        self._by_device_id: dict[str, ConnectedDevice] = {}

    def register(self, device: ConnectedDevice) -> None:
        """Құрылғыны тіркейді.

        Бір ``device_id`` бұрын басқа портта тіркелген болса, сол ескі
        port mapping жойылады. Duplicate ``port_name`` немесе
        ``device_id`` кездессе, соңғы жазба алдыңғысын ауыстырады.
        Ешбір exception сыртқа шықпайды.
        """
        try:
            existing_by_id = self._by_device_id.get(device.device_id)
            if existing_by_id is not None and existing_by_id.port_name != device.port_name:
                self._by_port.pop(existing_by_id.port_name, None)

            existing_by_port = self._by_port.get(device.port_name)
            if existing_by_port is not None and existing_by_port.device_id != device.device_id:
                self._by_device_id.pop(existing_by_port.device_id, None)

            self._by_port[device.port_name] = device
            self._by_device_id[device.device_id] = device
        except Exception:  # қорғаныс: болжанбаған қате де сыртқа шықпайды
            return

    def unregister_by_port(self, port_name: str) -> None:
        """Портқа сәйкес құрылғыны тіркеуден шығарады."""
        try:
            device = self._by_port.pop(port_name, None)
            if device is not None:
                self._by_device_id.pop(device.device_id, None)
        except Exception:
            return

    def get_by_port(self, port_name: str) -> ConnectedDevice | None:
        """Порт атауы бойынша тіркелген құрылғыны қайтарады."""
        try:
            return self._by_port.get(port_name)
        except Exception:
            return None

    def get_by_device_id(self, device_id: str) -> ConnectedDevice | None:
        """device_id бойынша тіркелген құрылғыны қайтарады."""
        try:
            return self._by_device_id.get(device_id)
        except Exception:
            return None

    def all_devices(self) -> tuple[ConnectedDevice, ...]:
        """Тіркелген барлық құрылғылардың жаңа tuple-ын қайтарады."""
        try:
            return tuple(self._by_port.values())
        except Exception:
            return ()

    def clear(self) -> None:
        """Барлық тіркелген құрылғыларды тазалайды."""
        try:
            self._by_port.clear()
            self._by_device_id.clear()
        except Exception:
            return
