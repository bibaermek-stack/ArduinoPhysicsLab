"""CalculationEngine — тексерілген негізгі мәндерден ExperimentDefinition
formulas конфигурациясына сай туынды физикалық шамаларды есептейтін таза
domain сервисі.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass

from core.constants import CURRENT_EPSILON
from domain.entities.experiment_definition import ExperimentDefinition

_CalculatorResult = tuple[float | None, str | None]
_Calculator = Callable[[dict[str, float], float | None], _CalculatorResult]


@dataclass(frozen=True)
class CalculationResult:
    """Есептелген туынды шамалардың нәтижесі."""

    values: dict[str, float]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]


class CalculationEngine:
    """definition.formulas ішінде көрсетілген derived channel кілттері
    бойынша алдын ала анықталған, қауіпсіз есептеу функцияларын шақыратын
    сервис. Формула мәтінін ешқашан орындамайды (eval қолданылмайды).
    """

    def __init__(self) -> None:
        self._calculators: dict[str, _Calculator] = {
            "resistance": self._calculate_resistance,
            "power": self._calculate_power,
            "work": self._calculate_work,
        }

    def calculate(
        self,
        values: dict[str, float],
        definition: ExperimentDefinition,
        elapsed_seconds: float | None = None,
    ) -> CalculationResult:
        """definition.formulas кілттері бойынша туынды шамаларды есептейді.
        values-ті өзгертпейді. Бір формуладағы қате қалған формулалардың
        есептелуіне кедергі жасамайды, ешбір exception сыртқа шықпайды.
        """
        results: dict[str, float] = {}
        warnings: list[str] = []
        errors: list[str] = []

        for channel_key in definition.formulas:
            calculator = self._calculators.get(channel_key)
            if calculator is None:
                warnings.append(f"'{channel_key}' үшін белгілі калькулятор жоқ")
                continue

            try:
                value, error = calculator(values, elapsed_seconds)
            except Exception as exc:  # қорғаныс: болжанбаған қате де сыртқа шықпайды
                errors.append(f"'{channel_key}': күтпеген есептеу қатесі — {exc}")
                continue

            if error is not None or value is None:
                errors.append(f"'{channel_key}': {error or 'есептелмеді'}")
                continue

            results[channel_key] = value

        return CalculationResult(
            values=results,
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    @staticmethod
    def _calculate_resistance(
        values: dict[str, float], elapsed_seconds: float | None
    ) -> _CalculatorResult:
        """R = U / I. Ток CURRENT_EPSILON-нан аз болса, бөлу орындалмайды."""
        voltage = values.get("voltage")
        current = values.get("current")
        if voltage is None:
            return None, "voltage мәні жоқ"
        if current is None:
            return None, "current мәні жоқ"
        if abs(current) < CURRENT_EPSILON:
            return None, "current нөлге тым жақын, resistance есептелмейді"

        result = voltage / current
        if not math.isfinite(result):
            return None, "есептелген resistance ақырлы (finite) сан емес"
        return result, None

    @staticmethod
    def _calculate_power(
        values: dict[str, float], elapsed_seconds: float | None
    ) -> _CalculatorResult:
        """P = U * I."""
        voltage = values.get("voltage")
        current = values.get("current")
        if voltage is None:
            return None, "voltage мәні жоқ"
        if current is None:
            return None, "current мәні жоқ"

        result = voltage * current
        if not math.isfinite(result):
            return None, "есептелген power ақырлы (finite) сан емес"
        return result, None

    @staticmethod
    def _calculate_work(
        values: dict[str, float], elapsed_seconds: float | None
    ) -> _CalculatorResult:
        """A = P * t. values ішінде 'power' болмаса, A = U * I * t
        формуласы қолданылады. Уақыт алдымен values['time']-тен, ол
        болмаса elapsed_seconds параметрінен алынады.
        """
        time_value = values.get("time")
        if time_value is None:
            time_value = elapsed_seconds
        if time_value is None:
            return None, "time де, elapsed_seconds да берілмеген"
        if time_value < 0:
            return None, "уақыт мәні теріс бола алмайды"

        power = values.get("power")
        if power is None:
            voltage = values.get("voltage")
            current = values.get("current")
            if voltage is None or current is None:
                return None, "work есептеу үшін power немесе (voltage, current) қажет"
            power = voltage * current

        result = power * time_value
        if not math.isfinite(result):
            return None, "есептелген work ақырлы (finite) сан емес"
        return result, None
