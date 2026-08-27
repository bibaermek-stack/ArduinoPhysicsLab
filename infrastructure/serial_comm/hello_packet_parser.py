"""hello_packet_parser — Arduino-дан келген HELLO handshake пакетін
(``TYPE=HELLO,DEV=...,MODEL=...,SENSOR=...,FW=...``) парсингтейтін модуль.

Бұл модуль measurement пакеттерін (``EXP=...``) өңдейтін
``infrastructure.serial_comm.packet_parser.PacketParser``-ден мүлдем
бөлек және оған тәуелді емес.
"""

from dataclasses import dataclass

_REQUIRED_KEYS = ("DEV", "MODEL", "SENSOR", "FW")
_KNOWN_KEYS = frozenset({"TYPE", "DEV", "MODEL", "SENSOR", "FW", "CHIP", "SERIAL", "HW"})


@dataclass(frozen=True)
class HelloParseResult:
    """HELLO пакетін парсингтеу нәтижесі."""

    success: bool
    device_id: str | None
    model: str | None
    sensor_type: str | None
    firmware_version: str | None
    chip: str | None
    serial_number: str | None
    hardware_version: str | None
    warnings: tuple[str, ...]
    errors: tuple[str, ...]


class HelloPacketParser:
    """``TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE,CHIP=INA226,FW=1.0``
    пішіміндегі handshake пакетін парсингтейтін сервис.
    """

    def parse(self, line: str) -> HelloParseResult:
        """Бір Serial жолын HELLO пакеті ретінде парсингтейді.

        ``line`` өзгертілмейді, ешбір exception сыртқа шықпайды.
        """
        try:
            return self._parse(line)
        except Exception as exc:  # қорғаныс: болжанбаған қате де сыртқа шықпайды
            return self._failure(f"Күтпеген HELLO парсинг қатесі: {exc}")

    def _parse(self, line: str) -> HelloParseResult:
        stripped_line = line.strip()
        if not stripped_line:
            return self._failure("Бос жол")

        fields: dict[str, str] = {}
        warnings: list[str] = []
        errors: list[str] = []
        seen_keys: set[str] = set()

        for raw_field in stripped_line.split(","):
            field = raw_field.strip()
            if not field:
                errors.append("бос өріс табылды")
                continue

            if "=" not in field:
                errors.append(f"'{field}' key=value форматында емес")
                continue

            key, _, value = field.partition("=")
            key = key.strip()
            value = value.strip()

            if not key:
                errors.append(f"'{field}' ішінде кілт бос")
                continue

            key_upper = key.upper()
            if key_upper in seen_keys:
                errors.append(f"'{key}' кілті бірнеше рет қайталанды")
                continue
            seen_keys.add(key_upper)

            if key_upper not in _KNOWN_KEYS:
                warnings.append(f"'{key}' белгісіз HELLO кілті, елеусіз қалды")
                continue

            fields[key_upper] = value

        if fields.get("TYPE") != "HELLO":
            errors.append("TYPE мәні 'HELLO' болуы керек")

        for required_key in _REQUIRED_KEYS:
            if not fields.get(required_key):
                errors.append(f"'{required_key}' мәні бос немесе жоқ")

        if errors:
            return HelloParseResult(
                success=False,
                device_id=None,
                model=None,
                sensor_type=None,
                firmware_version=None,
                chip=None,
                serial_number=None,
                hardware_version=None,
                warnings=tuple(warnings),
                errors=tuple(errors),
            )

        return HelloParseResult(
            success=True,
            device_id=fields.get("DEV"),
            model=fields.get("MODEL"),
            sensor_type=fields.get("SENSOR"),
            firmware_version=fields.get("FW"),
            chip=fields.get("CHIP"),
            serial_number=fields.get("SERIAL"),
            hardware_version=fields.get("HW"),
            warnings=tuple(warnings),
            errors=(),
        )

    @staticmethod
    def _failure(message: str) -> HelloParseResult:
        return HelloParseResult(
            success=False,
            device_id=None,
            model=None,
            sensor_type=None,
            firmware_version=None,
            chip=None,
            serial_number=None,
            hardware_version=None,
            warnings=(),
            errors=(message,),
        )
