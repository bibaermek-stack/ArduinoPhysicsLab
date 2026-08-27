"""IPhysicsModule — физикалық модульдің (Электр, Жылу, ...) "манифес" интерфейсі.

Әр модуль (мыс. ``ElectricityModule``) осы интерфейсті іске асырып, ModuleRegistry
арқылы қолмен тіркеледі және HomePage-те карточка ретінде көрсетіледі.
"""

from abc import ABC, abstractmethod

from domain.entities.experiment_definition import ExperimentDefinition


class IPhysicsModule(ABC):
    """Бір физикалық бөлімнің (модульдің) манифесі: аты, иконкасы және
    сол бөлімге қатысты зертхана жұмыстарының (ExperimentDefinition) тізімі.
    """

    @abstractmethod
    def get_name(self) -> str:
        """Модульдің пайдаланушыға көрсетілетін атауы."""
        raise NotImplementedError

    @abstractmethod
    def get_icon(self) -> str | None:
        """Модуль иконкасының resource жолы, немесе иконка жоқ болса ``None``."""
        raise NotImplementedError

    @abstractmethod
    def get_experiments(self) -> tuple[ExperimentDefinition, ...]:
        """Осы модульге қатысты зертхана жұмыстарының тізімі."""
        raise NotImplementedError
