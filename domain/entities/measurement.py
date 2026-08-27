"""Measurement — бір өлшем нүктесін сипаттайтын entity (timestamp, арна->мән)."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Measurement:
    timestamp: datetime
    values: dict[str, float]
    experiment_id: str
    derived_values: dict[str, float] = field(default_factory=dict)
    is_valid: bool = True
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.experiment_id:
            raise ValueError("experiment_id бос болмауы керек")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp timezone-aware болуы керек (мыс., UTC)")

        # frozen=True кезінде атрибутты тек object.__setattr__ арқылы орнатуға
        # болады. Осы арқылы values/derived_values-ке қорғаныш көшірме
        # жасалады (сыртқы dict-ке сілтеме қалдырылмайды) әрі барлық мән
        # float-қа түрлендіріледі.
        object.__setattr__(
            self, "values", {key: float(value) for key, value in self.values.items()}
        )
        object.__setattr__(
            self,
            "derived_values",
            {key: float(value) for key, value in self.derived_values.items()},
        )
        object.__setattr__(self, "warnings", tuple(self.warnings))

    def get_value(self, name: str) -> float | None:
        """Мәнді алдымен шикі values-тен, табылмаса derived_values-тен іздейді."""
        if name in self.values:
            return self.values[name]
        return self.derived_values.get(name)

    def all_values(self) -> dict[str, float]:
        """Шикі және есептелген мәндерді бір dict-ке біріктіріп қайтарады."""
        return {**self.values, **self.derived_values}
