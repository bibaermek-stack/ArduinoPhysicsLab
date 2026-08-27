"""ModuleRegistry — қолжетімді физикалық модульдерді қолмен тіркеу және
тізімдеу орталығы (автоматты discovery қолданылмайды).
"""

from domain.interfaces.i_physics_module import IPhysicsModule


class ModuleRegistry:
    """Тіркелген ``IPhysicsModule``-дерді жады ішінде (in-memory) сақтайтын
    registry. Тіркеу тек ``register()`` арқылы қолмен жасалады.
    """

    def __init__(self) -> None:
        self._modules: list[IPhysicsModule] = []

    def register(self, module: IPhysicsModule) -> None:
        """Модульді тізімге қосады."""
        self._modules.append(module)

    def get_all(self) -> tuple[IPhysicsModule, ...]:
        """Тіркелген барлық модульдердің тіркелу ретімен tuple-ын қайтарады."""
        return tuple(self._modules)
