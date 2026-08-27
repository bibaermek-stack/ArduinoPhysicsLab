"""packet_parser — Arduino-дан келген шикі (raw) Serial жолын
docs/serial_protocol.md хаттамасына сай құрылымдалған
PacketParseResult-қа айналдыратын модуль.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PacketParseResult:
    """Бір Serial жолын парсингтеу нәтижесі."""

    is_valid: bool
    experiment_id: str | None
    values: dict[str, float]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]


class PacketParser:
    """Arduino-дан Serial арқылы келген бір мәтіндік жолды
    ``EXP=E02,U=5.024,I=0.218,T=12.45`` пішіміне сай парсингтейтін сервис.
    """

    _KEY_MAP: dict[str, str] = {
        "U": "voltage",
        "I": "current",
        "T": "time",
        # Phase 38B: Metal-resistance-temperature (№8) — docs/serial_protocol.md
        # §10-де алдын ала жоспарланған кеңейту нүктесі. Әлі нақты firmware
        # жоқ (hardware adapter белсенді емес), бірақ парсинг дайын тұр.
        "TEMP": "temperature",
    }

    def parse_line(self, line: str) -> PacketParseResult:
        """Бір Serial жолын парсингтейді.

        ``line`` өзгертілмейді, ешбір exception сыртқа шықпайды —
        кез келген күтпеген жағдай ``PacketParseResult(is_valid=False, ...)``
        түрінде қайтарылады.
        """
        try:
            return self._parse_line(line)
        except Exception as exc:  # қорғаныс: болжанбаған қате де сыртқа шықпайды
            return PacketParseResult(
                is_valid=False,
                experiment_id=None,
                values={},
                warnings=(),
                errors=(f"Күтпеген парсинг қатесі: {exc}",),
            )

    def _parse_line(self, line: str) -> PacketParseResult:
        stripped_line = line.strip()
        if not stripped_line:
            return PacketParseResult(
                is_valid=False,
                experiment_id=None,
                values={},
                warnings=(),
                errors=("Бос жол",),
            )

        values: dict[str, float] = {}
        warnings: list[str] = []
        errors: list[str] = []
        experiment_id: str | None = None
        experiment_id_present = False
        seen_keys: set[str] = set()

        for raw_field in stripped_line.split(","):
            field = raw_field.strip()
            if not field:
                errors.append("бос өріс табылды")
                continue

            if "=" not in field:
                errors.append(f"'{field}' key=value форматында емес")
                continue

            key, _, raw_value = field.partition("=")
            key = key.strip()
            raw_value = raw_value.strip()

            if not key:
                errors.append(f"'{field}' ішінде кілт бос")
                continue

            if key in seen_keys:
                errors.append(f"'{key}' кілті бірнеше рет қайталанды")
                continue
            seen_keys.add(key)

            if key == "EXP":
                experiment_id_present = True
                if not raw_value:
                    errors.append("EXP мәні бос болмауы керек")
                    continue
                experiment_id = raw_value
                continue

            parsed_value, error = self._parse_numeric_value(key, raw_value)
            if error is not None or parsed_value is None:
                errors.append(error or f"'{key}': белгісіз қате")
                continue

            internal_key = self._KEY_MAP.get(key)
            if internal_key is not None:
                values[internal_key] = parsed_value
            else:
                lowered_key = key.lower()
                values[lowered_key] = parsed_value
                warnings.append(
                    f"'{key}' белгісіз кілт, values['{lowered_key}'] ретінде сақталды"
                )

        if not experiment_id_present:
            errors.append("EXP кілті міндетті")

        return PacketParseResult(
            is_valid=not errors,
            experiment_id=experiment_id,
            values=values,
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    @staticmethod
    def _parse_numeric_value(key: str, raw_value: str) -> tuple[float | None, str | None]:
        """Мәтіндік мәнді float-қа түрлендіреді.

        Мән әрқашан мәтін (``str``) түрінде келетіндіктен, "true"/"false"
        сияқты bool-тәрізді мәтіндер ``float()`` арқылы табиғи түрде
        қабылданбайды (``ValueError``) — яғни bool сан ретінде танылмайды.
        Сан емес немесе finite болмаса (NaN/Infinity), ``(None, error)``
        қайтарады.
        """
        try:
            parsed = float(raw_value)
        except ValueError:
            return None, f"'{key}': мән float-қа түрлендірілмейді ({raw_value!r})"
        if not math.isfinite(parsed):
            return None, f"'{key}': мән ақырлы (finite) сан болуы керек ({raw_value!r})"
        return parsed, None
