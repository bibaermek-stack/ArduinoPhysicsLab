"""SensorChannel — сенсор арнасының сипаттамасы (аты, өлшем бірлігі, min/max мән)."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SensorChannel:
    key: str
    display_name: str
    unit: str
    minimum: float | None = None
    maximum: float | None = None
    decimals: int = 2
    required: bool = True

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("key бос болмауы керек")
        if not self.display_name:
            raise ValueError("display_name бос болмауы керек")
        if self.decimals < 0:
            raise ValueError("decimals теріс сан бола алмайды")
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError("minimum мәні maximum мәнінен үлкен бола алмайды")

    def validate(self, value: float) -> tuple[bool, str | None]:
        """Берілген мәннің осы арнаға рұқсат етілген диапазонға сай екенін тексереді."""
        if not math.isfinite(value):
            return False, "Value must be a finite number."
        if self.minimum is not None and value < self.minimum:
            return False, (
                f"{self.display_name}: мән {value} рұқсат етілген минимумнан "
                f"({self.minimum}) төмен"
            )
        if self.maximum is not None and value > self.maximum:
            return False, (
                f"{self.display_name}: мән {value} рұқсат етілген максимумнан "
                f"({self.maximum}) жоғары"
            )
        return True, None
