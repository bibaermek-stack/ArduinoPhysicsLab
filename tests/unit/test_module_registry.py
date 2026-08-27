"""ModuleRegistry үшін юнит-тесттер."""

from domain.entities.experiment_definition import ExperimentDefinition
from domain.interfaces.i_physics_module import IPhysicsModule
from modules.module_registry import ModuleRegistry


class _FakeModule(IPhysicsModule):
    def __init__(self, name: str) -> None:
        self._name = name

    def get_name(self) -> str:
        return self._name

    def get_icon(self) -> str | None:
        return None

    def get_experiments(self) -> tuple[ExperimentDefinition, ...]:
        return ()


def test_empty_registry_returns_no_modules() -> None:
    registry = ModuleRegistry()

    assert registry.get_all() == ()


def test_register_adds_module() -> None:
    registry = ModuleRegistry()
    module = _FakeModule("Электр құбылыстары")

    registry.register(module)

    assert registry.get_all() == (module,)


def test_register_preserves_registration_order() -> None:
    registry = ModuleRegistry()
    first = _FakeModule("Бірінші")
    second = _FakeModule("Екінші")

    registry.register(first)
    registry.register(second)

    assert registry.get_all() == (first, second)
