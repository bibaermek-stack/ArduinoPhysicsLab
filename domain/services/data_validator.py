"""DataValidator — Arduino-дан келген шикі (raw) өлшем мәндерін
ExperimentDefinition конфигурациясындағы SensorChannel ережелеріне сай
тексеретін таза domain сервисі.
"""

from dataclasses import dataclass

from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.sensor_channel import SensorChannel


@dataclass(frozen=True)
class ValidationResult:
    """Бір raw measurement-ті тексеру нәтижесі."""

    is_valid: bool
    cleaned_values: dict[str, float]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]


class DataValidator:
    """raw_values сөздігін ExperimentDefinition.required_channels
    бойынша тексеретін сервис.
    """

    def validate(
        self, raw_values: dict[str, float], definition: ExperimentDefinition
    ) -> ValidationResult:
        """raw_values ішіндегі әр мәнді тиісті SensorChannel арқылы
        тексереді. raw_values-ті өзгертпейді, ешбір exception шығармай
        ValidationResult қайтарады.
        """
        try:
            return self._validate(raw_values, definition)
        except Exception as exc:  # қорғаныс: болжанбаған қате де сыртқа шықпайды
            return ValidationResult(
                is_valid=False,
                cleaned_values={},
                warnings=(),
                errors=(f"Күтпеген валидация қатесі: {exc}",),
            )

    def _validate(
        self, raw_values: dict[str, float], definition: ExperimentDefinition
    ) -> ValidationResult:
        channels_by_key: dict[str, SensorChannel] = {
            channel.key: channel for channel in definition.required_channels
        }

        cleaned_values: dict[str, float] = {}
        warnings: list[str] = []
        errors: list[str] = []

        for key, raw_value in raw_values.items():
            channel = channels_by_key.get(key)
            if channel is None:
                warnings.append(f"'{key}' арнасы ExperimentDefinition ішінде анықталмаған")
                continue

            numeric_value = self._to_float(raw_value)
            if numeric_value is None:
                errors.append(f"'{key}': мән float-қа түрлендірілмейді ({raw_value!r})")
                continue

            is_valid, message = channel.validate(numeric_value)
            if not is_valid:
                errors.append(message or f"'{key}': жарамсыз мән")
                continue

            cleaned_values[key] = numeric_value

        for channel in definition.required_channels:
            if channel.required and channel.key not in raw_values:
                errors.append(f"'{channel.key}' міндетті арнасы raw_values ішінде жоқ")

        return ValidationResult(
            is_valid=not errors,
            cleaned_values=cleaned_values,
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    @staticmethod
    def _to_float(value: object) -> float | None:
        """Мәнді қауіпсіз float-қа түрлендіреді. bool мәнін сан ретінде
        қабылдамайды, түрлендіру мүмкін болмаса None қайтарады.
        """
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        return None
