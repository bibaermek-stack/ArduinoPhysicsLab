"""ConnectedDevice — HELLO handshake арқылы анықталған Arduino негізіндегі
датчик құрылғысы туралы ақпарат.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ConnectedDevice:
    """Бір анықталған Serial құрылғысының өзгермейтін (immutable) жазбасы."""

    device_id: str
    model: str
    sensor_type: str
    firmware_version: str
    chip: str | None
    serial_number: str | None
    hardware_version: str | None
    port_name: str
    connected_at: datetime
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "device_id", self.device_id.strip())
        object.__setattr__(self, "model", self.model.strip())
        object.__setattr__(self, "sensor_type", self.sensor_type.strip())
        object.__setattr__(self, "firmware_version", self.firmware_version.strip())
        object.__setattr__(self, "port_name", self.port_name.strip())
        object.__setattr__(self, "chip", self._stripped_or_none(self.chip))
        object.__setattr__(self, "serial_number", self._stripped_or_none(self.serial_number))
        object.__setattr__(
            self, "hardware_version", self._stripped_or_none(self.hardware_version)
        )
        object.__setattr__(self, "warnings", tuple(self.warnings))

        if not self.device_id:
            raise ValueError("device_id бос болмауы керек")
        if not self.model:
            raise ValueError("model бос болмауы керек")
        if not self.sensor_type:
            raise ValueError("sensor_type бос болмауы керек")
        if not self.firmware_version:
            raise ValueError("firmware_version бос болмауы керек")
        if self.connected_at.tzinfo is None:
            raise ValueError("connected_at timezone-aware болуы керек (мыс., UTC)")

    @staticmethod
    def _stripped_or_none(value: str | None) -> str | None:
        """Қосымша (optional) мәтіндік өрісті strip() етеді; strip-тен
        кейін бос болса, ``None`` қайтарады.
        """
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None
