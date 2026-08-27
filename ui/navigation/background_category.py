"""background_category — route/модуль атауын WorkspaceBackdrop-тың секция
кілтіне бейнелейтін таза (Qt-сыз) функциялар (Phase 41).

``ui.pages.experiment_list_page._SECTION_ACCENT_BY_NAME``-мен бірдей
мағынадағы, БІРАҚ бөлек презентациялық қажеттілік үшін қасақана
қайталанған кесте — жобаның бұрыннан бар "кіші lookup сөздігін файл
арасында дублирлеу" конвенциясы (§ ``_SENSOR_TYPE_NAMES_KK``
device_card.py/device_panel.py арасында, ``_SECTION_ACCENT_BY_NAME``
experiment_list_page.py/home_page.py арасында).
"""

from __future__ import annotations

CATEGORY_HOME = "home"
CATEGORY_HEAT = "heat"
CATEGORY_ELECTRICITY = "electricity"
CATEGORY_ELECTROMAGNETISM = "electromagnetism"
CATEGORY_LIGHT = "light"
CATEGORY_LABORATORY = "laboratory"
CATEGORY_RESULTS = "results"
CATEGORY_FEEDBACK = "feedback"
CATEGORY_DEVICES = "devices"
CATEGORY_ANALYTICS = "analytics"
CATEGORY_HELP = "help"
CATEGORY_DEFAULT = "default"

ALL_CATEGORIES: tuple[str, ...] = (
    CATEGORY_HOME,
    CATEGORY_HEAT,
    CATEGORY_ELECTRICITY,
    CATEGORY_ELECTROMAGNETISM,
    CATEGORY_LIGHT,
    CATEGORY_LABORATORY,
    CATEGORY_RESULTS,
    CATEGORY_FEEDBACK,
    CATEGORY_DEVICES,
    CATEGORY_ANALYTICS,
    CATEGORY_HELP,
    CATEGORY_DEFAULT,
)

# Router route атауы -> фон секциясы. Тізімде жоқ ЕШБІР route
# CATEGORY_DEFAULT-тан асып қателеспейді (resolve_route_category әрқашан
# қауіпсіз мән қайтарады).
_ROUTE_CATEGORY: dict[str, str] = {
    "home": CATEGORY_HOME,
    "dashboard": CATEGORY_HOME,
    "experiment_list": CATEGORY_LABORATORY,
    "data_journal": CATEGORY_RESULTS,
    "my_results": CATEGORY_RESULTS,
    "results": CATEGORY_RESULTS,
    "feedback_student": CATEGORY_FEEDBACK,
    "feedback_teacher": CATEGORY_FEEDBACK,
    "devices": CATEGORY_DEVICES,
    "analytics": CATEGORY_ANALYTICS,
    "about": CATEGORY_HELP,
}

# ExperimentWorkspacePage.current_module_accent_key()-дан келетін кілт ->
# фон секциясы (experiment_list_page._SECTION_ACCENT_BY_NAME-дың
# мәндерімен бірдей: "heat"/"electricity"/"electromagnetism"/"light").
_MODULE_ACCENT_CATEGORY: dict[str, str] = {
    "heat": CATEGORY_HEAT,
    "electricity": CATEGORY_ELECTRICITY,
    "electromagnetism": CATEGORY_ELECTROMAGNETISM,
    "light": CATEGORY_LIGHT,
}


def resolve_route_category(route: str) -> str:
    """Router route атауын фон секциясына бейнелейді.

    Белгісіз/жіктелмеген route-тар үшін ЕШҚАШАН exception шығармайды —
    әрқашан ``CATEGORY_DEFAULT``-қа сай келеді (§ "Every route must have
    a safe fallback background").
    """
    return _ROUTE_CATEGORY.get(route, CATEGORY_DEFAULT)


def resolve_experiment_category(module_accent_key: str | None) -> str:
    """``experiment_workspace`` route-ы үшін нақты физика модулінің
    ("heat"/"electricity"/"electromagnetism"/"light") фон секциясын
    қайтарады. Модуль табылмаса (``None``) — жалпы зертхана секциясына
    (``CATEGORY_LABORATORY``) сай келеді, ешқашан жарамсыз кілтпен
    құламайды.
    """
    if module_accent_key is None:
        return CATEGORY_LABORATORY
    return _MODULE_ACCENT_CATEGORY.get(module_accent_key, CATEGORY_LABORATORY)
