"""device_scanner — қолжетімді COM-порттар тізімін QSerialPortInfo арқылы
алатын және Arduino-ға ұқсас құрылғыларды анықтайтын модуль.
"""

from dataclasses import dataclass

from PySide6.QtSerialPort import QSerialPortInfo

# Белгілі Arduino/Arduino-үйлесімді USB-Serial чиптердің vendor ID мәндері.
_KNOWN_ARDUINO_VENDOR_IDS: frozenset[int] = frozenset(
    {
        0x2341,  # Arduino LLC
        0x2A03,  # Arduino SA
        0x1A86,  # QinHeng Electronics (CH340)
        0x10C4,  # Silicon Labs (CP210x)
        0x0403,  # FTDI
    }
)


@dataclass(frozen=True)
class SerialDeviceInfo:
    """Бір қолжетімді Serial құрылғысы туралы ақпарат."""

    port_name: str
    description: str
    manufacturer: str | None
    serial_number: str | None
    vendor_id: int | None
    product_id: int | None
    is_likely_arduino: bool


class DeviceScanner:
    """Жүйедегі қолжетімді COM-порттарды тізімдейтін сервис."""

    def scan(self) -> tuple[SerialDeviceInfo, ...]:
        """Қолжетімді барлық Serial порттарды тізімдейді.

        Нәтиже ``port_name`` бойынша сұрыпталған, әр шақырғанда жаңа
        tuple түрінде қайтарылады. Ешбір exception сыртқа шықпайды.
        """
        try:
            ports = list(QSerialPortInfo.availablePorts())
            devices = [self._to_device_info(port) for port in ports]
            devices.sort(key=lambda device: device.port_name)
            return tuple(devices)
        except Exception:  # қорғаныс: болжанбаған қате де сыртқа шықпайды
            return ()

    def _to_device_info(self, port: QSerialPortInfo) -> SerialDeviceInfo:
        """Бір ``QSerialPortInfo`` жазбасын ``SerialDeviceInfo``-ға айналдырады."""
        vendor_id = port.vendorIdentifier() if port.hasVendorIdentifier() else None
        product_id = port.productIdentifier() if port.hasProductIdentifier() else None
        manufacturer = port.manufacturer() or None
        serial_number = port.serialNumber() or None
        description = port.description()

        return SerialDeviceInfo(
            port_name=port.portName(),
            description=description,
            manufacturer=manufacturer,
            serial_number=serial_number,
            vendor_id=vendor_id,
            product_id=product_id,
            is_likely_arduino=self._is_likely_arduino(
                description=description,
                manufacturer=manufacturer,
                vendor_id=vendor_id,
            ),
        )

    @staticmethod
    def _is_likely_arduino(
        description: str, manufacturer: str | None, vendor_id: int | None
    ) -> bool:
        """Vendor ID белгілі тізімде болса немесе description/manufacturer
        ішінде "arduino" сөзі кездессе, True қайтарады.
        """
        if vendor_id is not None and vendor_id in _KNOWN_ARDUINO_VENDOR_IDS:
            return True

        haystack = f"{description} {manufacturer or ''}".lower()
        return "arduino" in haystack
