"""ExperimentSession — бір тәжірибе сеансының толық жазбасы (Measurement тізімі, метадата)."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from domain.entities.measurement import Measurement


@dataclass
class ExperimentSession:
    id: str
    experiment_id: str
    started_at: datetime
    ended_at: datetime | None = None
    measurements: list[Measurement] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id бос болмауы керек")
        if not self.experiment_id:
            raise ValueError("experiment_id бос болмауы керек")
        if self.started_at.tzinfo is None:
            raise ValueError("started_at timezone-aware болуы керек (мыс., UTC)")
        if self.ended_at is not None and self.ended_at.tzinfo is None:
            raise ValueError("ended_at timezone-aware болуы керек (мыс., UTC)")

    @property
    def measurement_count(self) -> int:
        return len(self.measurements)

    def add_measurement(self, measurement: Measurement) -> None:
        """Өлшемді сессияға қосады. experiment_id сәйкес келмесе ValueError шығарады."""
        if measurement.experiment_id != self.experiment_id:
            raise ValueError(
                f"Measurement.experiment_id ('{measurement.experiment_id}') "
                f"ExperimentSession.experiment_id ('{self.experiment_id}') мәнімен сәйкес келмейді"
            )
        self.measurements.append(measurement)

    def stop(self) -> None:
        """Сессияны аяқтайды. Қайта шақырылса ended_at мәні өзгермейді."""
        if self.ended_at is None:
            self.ended_at = datetime.now(timezone.utc)

    def clear(self) -> None:
        """Жиналған барлық өлшемдерді тазалайды (сессияның өзін аяқтамайды)."""
        self.measurements.clear()

    def duration_seconds(self) -> float:
        """Сессияның ұзақтығы. Әлі жүріп жатса, ағымдағы UTC уақытқа дейін есептеледі."""
        end = self.ended_at if self.ended_at is not None else datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()
