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

    Жұмыс (``work``) лездік ``P × t`` емес — өлшем ағыны бойынша
    трапеция ережесімен ``A = ∫ P(t) dt``. Жаңа сессия алдында
    ``reset()`` шақырылуы тиіс.
    """

    def __init__(self) -> None:
        self._calculators: dict[str, _Calculator] = {
            "resistance": self._calculate_resistance,
            "power": self._calculate_power,
            "work": self._calculate_work,
        }
        self.reset()

    def reset(self) -> None:
        """Жұмыс интегралының күйін жаңа өлшеу сессиясы үшін тазалайды."""
        self._work_time: float | None = None
        self._work_power: float | None = None
        self._work_sum: float = 0.0

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

    def _calculate_work(
        self, values: dict[str, float], elapsed_seconds: float | None
    ) -> _CalculatorResult:
        """A = ∫ P(t) dt (трапеция ережесі). Тұрақты P кезінде бұл
        ``P × Δt``-ға тең; лездік ``P × t_elapsed`` қолданылмайды —
        қуат өзгерсе қате жинақталмас үшін. Бірінші үлгіде аралық жоқ,
        сондықтан жұмыс 0. Уақыт ``values['time']`` немесе
        ``elapsed_seconds``. ``power`` жоқ болса P = U × I.
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

        if not math.isfinite(power):
            return None, "есептелген power ақырлы (finite) сан емес"

        if self._work_time is None or self._work_power is None:
            self._work_time = time_value
            self._work_power = power
            self._work_sum = 0.0
            return 0.0, None

        dt = time_value - self._work_time
        if dt > 0:
            self._work_sum += 0.5 * (self._work_power + power) * dt
        self._work_time = time_value
        self._work_power = power
        if not math.isfinite(self._work_sum):
            return None, "есептелген work ақырлы (finite) сан емес"
        return self._work_sum, None
