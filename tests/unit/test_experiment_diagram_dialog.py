"""ExperimentDiagramDialog (Phase 36.1) үшін юнит-тесттер: сурет жүктелуі,
aspect ratio сақталуы, zoom in/out/reset/fit, caption көрсетілуі, Жабу
батырмасы, қайталап ашу/жабу кезінде виджет жинақталмауы.
"""

import sys
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QScrollArea

from domain.entities.experiment_definition import ExperimentDiagram
from ui.widgets.experiment_diagram_dialog import ExperimentDiagramDialog

_REAL_IMAGE_PATH = str(
    Path(__file__).resolve().parents[2]
    / "ui"
    / "resources"
    / "images"
    / "current_voltage_wiring.png"
)


@pytest.fixture(scope="module", autouse=True)
def qt_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _diagram(caption: str = "") -> ExperimentDiagram:
    return ExperimentDiagram(image_path=_REAL_IMAGE_PATH, caption=caption)


def test_dialog_shows_experiment_title_and_subtitle() -> None:
    dialog = ExperimentDiagramDialog("Электр тізбегін құрастыру және ток күшін өлшеу", _diagram())

    assert "Электр тізбегін құрастыру және ток күшін өлшеу" in dialog.windowTitle()
    assert "Қосылу схемасы" in dialog.windowTitle()
    dialog.close()


def test_dialog_contains_scroll_area() -> None:
    dialog = ExperimentDiagramDialog("Электр тізбегін құрастыру және ток күшін өлшеу", _diagram())

    scroll_areas = dialog.findChildren(QScrollArea)

    assert len(scroll_areas) == 1
    dialog.close()


def test_image_loads_successfully_without_show() -> None:
    """Сурет ЕШҚАШАН бос болмауы тиіс — show() шақырылмаса да."""
    dialog = ExperimentDiagramDialog("Электр тізбегін құрастыру және ток күшін өлшеу", _diagram())

    assert dialog._original_pixmap.isNull() is False
    assert dialog._image_label.pixmap().isNull() is False
    dialog.close()


def test_aspect_ratio_preserved_at_default_scale() -> None:
    dialog = ExperimentDiagramDialog("Электр тізбегін құрастыру және ток күшін өлшеу", _diagram())

    original = dialog._original_pixmap
    scaled = dialog._image_label.pixmap()
    original_ratio = original.width() / original.height()
    scaled_ratio = scaled.width() / scaled.height()

    assert abs(original_ratio - scaled_ratio) < 0.01
    dialog.close()


def test_zoom_in_increases_zoom_factor_and_rescales() -> None:
    dialog = ExperimentDiagramDialog("Электр тізбегін құрастыру және ток күшін өлшеу", _diagram())
    initial_factor = dialog._zoom_factor
    initial_size = dialog._image_label.pixmap().size()

    dialog._on_zoom_in_clicked()

    assert dialog._zoom_factor > initial_factor
    assert dialog._image_label.pixmap().width() > initial_size.width()
    dialog.close()


def test_zoom_out_decreases_zoom_factor_and_rescales() -> None:
    dialog = ExperimentDiagramDialog("Электр тізбегін құрастыру және ток күшін өлшеу", _diagram())
    initial_factor = dialog._zoom_factor
    initial_size = dialog._image_label.pixmap().size()

    dialog._on_zoom_out_clicked()

    assert dialog._zoom_factor < initial_factor
    assert dialog._image_label.pixmap().width() < initial_size.width()
    dialog.close()


def test_zoom_in_clamps_at_maximum() -> None:
    dialog = ExperimentDiagramDialog("Электр тізбегін құрастыру және ток күшін өлшеу", _diagram())

    for _ in range(200):
        dialog._on_zoom_in_clicked()

    assert dialog._zoom_factor == pytest.approx(4.0)
    dialog.close()


def test_zoom_out_clamps_at_minimum() -> None:
    dialog = ExperimentDiagramDialog("Электр тізбегін құрастыру және ток күшін өлшеу", _diagram())

    for _ in range(200):
        dialog._on_zoom_out_clicked()

    assert dialog._zoom_factor == pytest.approx(0.25)
    dialog.close()


def test_reset_and_fit_to_window_are_the_same_operation() -> None:
    """Спецификация "Қалпына келтіру"-ды "returns to default fit" деп
    анықтайды — сондықтан екі батырма да БІРДЕЙ нәтиже беруі тиіс.
    """
    dialog = ExperimentDiagramDialog("Электр тізбегін құрастыру және ток күшін өлшеу", _diagram())
    dialog.show()
    dialog._on_zoom_in_clicked()
    dialog._on_zoom_in_clicked()

    dialog._on_fit_to_window_clicked()
    factor_after_fit = dialog._zoom_factor

    dialog._on_zoom_in_clicked()
    dialog._on_zoom_in_clicked()
    dialog._reset_button.click()
    factor_after_reset = dialog._zoom_factor

    assert factor_after_reset == pytest.approx(factor_after_fit)
    dialog.close()


def test_fit_to_window_applied_automatically_on_show() -> None:
    dialog = ExperimentDiagramDialog("Электр тізбегін құрастыру және ток күшін өлшеу", _diagram())
    QApplication.instance().processEvents()

    dialog.show()
    QApplication.instance().processEvents()

    # showEvent() көрінген сәтте нақты geometry негізінде fit-ты
    # автоматты қолданады — бастапқы (show() дейінгі) 1.0 мәнінен
    # өзгеше болуы тиіс (нақты диалог өлшемі 893x505 суретке дәл 1:1
    # келмейді).
    assert dialog._zoom_factor != pytest.approx(1.0)
    dialog.close()


def test_caption_shown_when_present() -> None:
    dialog = ExperimentDiagramDialog("Электр тізбегін құрастыру және ток күшін өлшеу", _diagram(caption="Қызыл сым — оң полюс."))

    assert dialog._caption_label is not None
    assert dialog._caption_label.text() == "Қызыл сым — оң полюс."
    dialog.close()


def test_caption_hidden_when_empty() -> None:
    dialog = ExperimentDiagramDialog("Электр тізбегін құрастыру және ток күшін өлшеу", _diagram())

    assert dialog._caption_label is None
    dialog.close()


def test_dialog_has_close_button_that_closes_dialog() -> None:
    dialog = ExperimentDiagramDialog("Электр тізбегін құрастыру және ток күшін өлшеу", _diagram())
    dialog.show()
    assert dialog.isVisible() is True

    dialog._close_button.click()

    assert dialog.isVisible() is False


def test_repeated_construction_does_not_accumulate_top_level_widgets() -> None:
    """Нақты пайдалану (``ExperimentWorkspacePage``) әр басу сайын
    ``WA_DeleteOnClose`` орнатады — дәл сол шартты осында да қайталаймыз,
    әйтпесе ``close()`` жай ғана жасырады, C++ данасын жоймайды.
    """
    app = QApplication.instance()
    baseline = len(app.topLevelWidgets())

    for _ in range(5):
        dialog = ExperimentDiagramDialog("Электр тізбегін құрастыру және ток күшін өлшеу", _diagram())
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.show()
        dialog.close()
    app.processEvents()

    assert len(app.topLevelWidgets()) == baseline


def test_dialog_never_touches_unrelated_state() -> None:
    """Архитектуралық кепілдік: диалог тек title/diagram алады — ешбір
    graph/measurement/coordinator сілтемесі жоқ, сондықтан ашу/жабу
    оларға ЕШҚАШАН тие алмайды (Guide/Report диалогтарымен БІРДЕЙ
    оқшаулау принципі).
    """
    import inspect

    signature = inspect.signature(ExperimentDiagramDialog.__init__)
    assert set(signature.parameters.keys()) == {"self", "experiment_title", "diagram", "parent"}
