"""DeviceRegistry үшін юнит-тесттер."""

from datetime import datetime, timezone

from domain.entities.connected_device import ConnectedDevice
from domain.services.device_registry import DeviceRegistry


def _make_device(
    device_id: str = "APL-VOLTAGE-01",
    sensor_type: str = "VOLTAGE",
    port_name: str = "COM3",
) -> ConnectedDevice:
    return ConnectedDevice(
        device_id=device_id,
        model="V1",
        sensor_type=sensor_type,
        firmware_version="1.0",
        chip="INA226",
        serial_number=None,
        hardware_version=None,
        port_name=port_name,
        connected_at=datetime.now(timezone.utc),
        warnings=(),
    )


def test_register_and_get_by_port() -> None:
    registry = DeviceRegistry()
    device = _make_device(port_name="COM3")

    registry.register(device)

    assert registry.get_by_port("COM3") == device


def test_register_and_get_by_device_id() -> None:
    registry = DeviceRegistry()
    device = _make_device(device_id="APL-CURRENT-01")

    registry.register(device)

    assert registry.get_by_device_id("APL-CURRENT-01") == device


def test_duplicate_port_replaces_old_device() -> None:
    registry = DeviceRegistry()
    old_device = _make_device(device_id="APL-VOLTAGE-01", port_name="COM3")
    new_device = _make_device(device_id="APL-CURRENT-01", port_name="COM3")

    registry.register(old_device)
    registry.register(new_device)

    assert registry.get_by_port("COM3") == new_device
    assert registry.get_by_device_id("APL-VOLTAGE-01") is None
    assert registry.get_by_device_id("APL-CURRENT-01") == new_device


def test_device_moves_to_new_port() -> None:
    registry = DeviceRegistry()
    device_on_old_port = _make_device(device_id="APL-VOLTAGE-01", port_name="COM3")
    device_on_new_port = _make_device(device_id="APL-VOLTAGE-01", port_name="COM5")

    registry.register(device_on_old_port)
    registry.register(device_on_new_port)

    assert registry.get_by_port("COM3") is None
    assert registry.get_by_port("COM5") == device_on_new_port
    assert registry.get_by_device_id("APL-VOLTAGE-01") == device_on_new_port


def test_unregister_by_port() -> None:
    registry = DeviceRegistry()
    device = _make_device(port_name="COM3")
    registry.register(device)

    registry.unregister_by_port("COM3")

    assert registry.get_by_port("COM3") is None
    assert registry.get_by_device_id(device.device_id) is None


def test_clear_removes_all_devices() -> None:
    registry = DeviceRegistry()
    registry.register(_make_device(device_id="APL-VOLTAGE-01", port_name="COM3"))
    registry.register(_make_device(device_id="APL-CURRENT-01", port_name="COM5"))

    registry.clear()

    assert registry.all_devices() == ()
    assert registry.get_by_port("COM3") is None
    assert registry.get_by_device_id("APL-CURRENT-01") is None
