"""Router — QStackedWidget ішіндегі беттер арасында ауысуды басқаратын сервис.

Әр бет ``on_enter(**params)`` әдісін анықтаса (duck-typing — Router бұл
әдістің бар-жоғын тек ``hasattr`` арқылы тексереді), ``navigate()`` бетті
көрсетпес бұрын сол әдіске параметрлерді жеткізеді. Параметрі жоқ беттер
(мыс. HomePage) ``on_enter``-ді анықтамай-ақ қолдана береді.

Phase 37A: ``is_route_allowed`` — рөлге негізделген навигацияны шектеу
үшін ЕРІКТІ guard hook (әдепкі ``None`` — шексіз, ескі/басқа Router
қолданушыларына ЕШБІР әсер етпейді). ``MainWindow`` мұны ағымдағы рөлге
байланысты route-тарды тексеретін функциямен береді — тіпті "тікелей"
(sidebar батырмасынсыз) ``navigate()`` шақыруы да рұқсат етілмеген
route-қа ешқашан бармайды.
"""

import logging
import traceback
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QStackedWidget, QWidget

_logger = logging.getLogger(__name__)
# УАҚЫТША ДИАГНОСТИКА (§ main.py-дегі debug.log).
_trace_logger = logging.getLogger("apl.trace")


class Router(QObject):
    """``QStackedWidget`` үстінде беттерді атау бойынша тіркеп, солар
    арасында ауысуды басқаратын жеңіл навигация сервисі.
    """

    # Phase 41: жұмыс кеңістігі фонын (WorkspaceBackdrop) route-қа
    # байланысты жаңарту үшін — ТЕК сәтті (guard рұқсат еткен) ауысу
    # кезінде эмитацияланады, guard тоқтатқан "тайдырылған" navigate()
    # шақыруларында ЕШҚАШАН емес.
    route_changed = Signal(str)

    def __init__(
        self,
        stack: QStackedWidget,
        is_route_allowed: Callable[[str], bool] | None = None,
    ) -> None:
        super().__init__()
        self._stack = stack
        self._pages: dict[str, QWidget] = {}
        self._is_route_allowed = is_route_allowed

    def register(self, name: str, page: QWidget) -> None:
        """Бетті ``name`` атауымен тіркеп, стекке бір рет қосады."""
        if name in self._pages:
            raise ValueError(f"'{name}' атауымен бет бұрын тіркелген")
        self._pages[name] = page
        self._stack.addWidget(page)
        # 12. УАҚЫТША ДИАГНОСТИКА.
        _trace_logger.info("12. Router.register('%s', %s id=%s)", name, type(page).__name__, id(page))

    def navigate(self, name: str, **params: object) -> bool:
        """Тіркелген бетке ауысады. Бетте ``on_enter`` әдісі анықталса,
        ауысу алдында соған ``params`` жеткізіледі.

        ``is_route_allowed`` берілген және ``name`` үшін ``False``
        қайтарса, ауысу ЖАСАЛМАЙДЫ (ағымдағы бет өзгеріссіз қалады) және
        ``False`` қайтарылады — ешбір exception шығармайды.
        """
        # 13. УАҚЫТША ДИАГНОСТИКА.
        _trace_logger.info("13. Router.navigate('%s', params=%s) called", name, list(params.keys()))
        if self._is_route_allowed is not None and not self._is_route_allowed(name):
            _logger.debug("navigate('%s') рұқсат етілмеген рөл үшін — тайдырылды", name)
            _trace_logger.info("    -> BLOCKED by is_route_allowed guard")
            return False
        try:
            page = self._pages[name]
        except KeyError:
            _trace_logger.critical(
                "    -> KeyError: route '%s' is NOT registered. Known routes: %s",
                name, list(self._pages.keys()),
            )
            raise
        try:
            on_enter = getattr(page, "on_enter", None)
            if callable(on_enter):
                on_enter(**params)
            self._stack.setCurrentWidget(page)
            self.route_changed.emit(name)
        except Exception:
            _trace_logger.critical(
                "16. EXCEPTION during navigate('%s'):\n%s", name, traceback.format_exc()
            )
            raise
        _trace_logger.info("    -> navigate('%s') succeeded, current page=%s", name, type(page).__name__)
        return True
