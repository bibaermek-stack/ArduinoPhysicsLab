"""QuestionBankPage — "Сұрақтар банкі" беті (Phase 20, Мұғалім-тек).

Бұрынғы ``PlaceholderPage``-тің орнына. Бұл бет ЕШБІР жаңа, Мұғалім-тек
параллель сұрақ дерекқорын құрмайды — ``IQuestionRepository`` дәл СОЛ
``domain.entities.experiment_assessment`` типтерін (``MultipleChoiceQuestion``/
``OpenResponseQuestion``/``ReflectionQuestion``) сақтайды, әрі
``ExperimentWorkspacePage`` осы ЖАЛҒЫЗ репозиторийден оқиды (§
``domain/services/question_bank_assembly.py`` — "reuse the same
underlying questions that the student workflow uses").

Барлық есептеу (KPI/сүзгі/сұрыптау) Qt-сыз таза функцияларда орындалады
(§ Analytics бетімен БІРДЕЙ принцип, "Do not put business logic directly
into the page").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from domain.entities.experiment_assessment import (
    MultipleChoiceQuestion,
    OpenResponseQuestion,
    ReflectionQuestion,
)
from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.question_record import QuestionContent, QuestionRecord
from domain.entities.user_role import UserRole
from domain.interfaces.i_question_repository import IQuestionRepository
from modules.module_registry import ModuleRegistry
from ui.themes.theme_manager import COLOR_ACCENT, COLOR_INFO, COLOR_SUCCESS, COLOR_TEXT_MUTED

_PAGE_TITLE = "Сұрақтар банкі"
_PAGE_SUBTITLE = "Зертханалық жұмыстарға арналған бақылау сұрақтарын дайындау және басқару."

_ALL_FILTER_TEXT = "Барлығы"
_NO_VALUE_TEXT = "—"
_FILTER_COMBO_MAX_WIDTH = 210
_LEVEL_FILTER_MAX_WIDTH = 130
_STATUS_FILTER_MAX_WIDTH = 150

_SEARCH_PLACEHOLDER_TEXT = "Сұрақты іздеу..."
_ADD_QUESTION_TEXT = "+ Сұрақ қосу"
_EDIT_TEXT = "Өңдеу"
_DELETE_TEXT = "Өшіру"

_STATUS_ACTIVE_KEY = "active"
_STATUS_INACTIVE_KEY = "inactive"
_STATUS_FILTER_OPTIONS: tuple[tuple[str, str], ...] = (
    (_STATUS_ACTIVE_KEY, "Белсенді"),
    (_STATUS_INACTIVE_KEY, "Белсенді емес"),
)
_STATUS_TEXT = {True: "Белсенді", False: "Белсенді емес"}
_STATUS_COLOR = {True: COLOR_SUCCESS, False: COLOR_TEXT_MUTED}

_LEVEL_OPTIONS: tuple[tuple[int, str], ...] = ((1, "1-деңгей"), (2, "2-деңгей"), (3, "3-деңгей"))
_LEVEL_TEXT = {1: "1-деңгей", 2: "2-деңгей", 3: "3-деңгей"}
# §7 "subtle badges/colors using existing semantic tokens... not a loud
# rainbow design" — тек ЕКІ акцент + бейтарап (§ бар токендер, жаңа түс
# ойлап шығарылмайды).
_LEVEL_COLOR = {1: COLOR_ACCENT, 2: COLOR_INFO, 3: None}

_TABLE_HEADERS = ("№", "Зертханалық жұмыс", "Деңгей", "Сұрақ", "Күйі", "Әрекет")
_QUESTION_COLUMN_INDEX = 3
_ACTION_COLUMN_INDEX = 5

_EMPTY_REPOSITORY_TITLE = "Сұрақтар әлі қосылмаған."
_EMPTY_REPOSITORY_HINT = "Зертханалық жұмыстарға арналған алғашқы бақылау сұрағын қосыңыз."
_EMPTY_FILTERED_TITLE = "Таңдалған сүзгіге сай сұрақтар табылмады."
_EMPTY_FILTERED_HINT = "Іздеу немесе сүзгі параметрлерін өзгертіп көріңіз."

_DELETE_CONFIRM_TITLE = "Сұрақты өшіру"
_DELETE_CONFIRM_TEXT = "Бұл сұрақты өшіргіңіз келе ме?"
_DELETE_CONFIRM_BUTTON = "Өшіру"
_DELETE_CANCEL_BUTTON = "Болдырмау"

_MIN_OPTIONS = 2


def _make_background_transparent(widget: QWidget) -> None:
    """§ ``teacher_dashboard_page._make_background_transparent()``-мен
    БІРДЕЙ себеп/түзету — ``role``-негізді ``QLabel`` өз ЕНІНЕ (QVBoxLayout-
    та толық созылған) сай ``COLOR_BACKGROUND`` тіктөртбұрышын ақ
    ``HomeSummaryCard`` үстінде бояп кетеді. instance-деңгейлік
    ``setStyleSheet()`` ғана жұмыс істейді."""
    widget.setStyleSheet("background-color: transparent;")


# ==========================================================================
# ТАЗА ЕСЕПТЕУ ҚАБАТЫ (Qt-сыз)
# ==========================================================================


def iter_catalog_experiments(module_registry: ModuleRegistry) -> tuple[ExperimentDefinition, ...]:
    experiments: list[ExperimentDefinition] = []
    for module in module_registry.get_all():
        experiments.extend(module.get_experiments())
    return tuple(experiments)


@dataclass(frozen=True)
class QuestionBankKpis:
    total_text: str
    experiments_with_questions_text: str
    active_text: str
    average_text: str


def compute_kpis(all_records: tuple[QuestionRecord, ...]) -> QuestionBankKpis:
    """§4 — ``all_records`` белсенді+мұрағатталған БАРЛЫҒЫН қамтуы тиіс
    (шақырушы ``list_all(include_archived=True)`` береді).

    - Барлық сұрақтар: барлық персистентелген жазба саны (белсенді +
      мұрағатталған).
    - Зертханалық жұмыстар: қазір кемінде БІР БЕЛСЕНДІ сұрағы бар
      бірегей ``experiment_id`` саны.
    - Белсенді сұрақтар: тек ``is_active=True`` саны.
    - Орташа сұрақ саны: белсенді сұрақ саны / сол белсенді сұрақтары
      бар тәжірибе саны (§ "questions / experiments that have
      questions" — бөлгіш ТЕК қазір белсенді сұрағы бар тәжірибелер,
      бүкіл каталог емес). Бөлгіш 0 болса "—".
    """
    total = len(all_records)
    active_records = tuple(r for r in all_records if r.is_active)
    active_count = len(active_records)
    experiments_with_active = {r.experiment_id for r in active_records}

    average_text = (
        f"{active_count / len(experiments_with_active):.1f}"
        if experiments_with_active
        else _NO_VALUE_TEXT
    )

    return QuestionBankKpis(
        total_text=str(total),
        experiments_with_questions_text=str(len(experiments_with_active)),
        active_text=str(active_count),
        average_text=average_text,
    )


def filter_records(
    records: tuple[QuestionRecord, ...],
    experiment_id: str | None,
    level: int | None,
    status_key: str | None,
    search_text: str,
) -> tuple[QuestionRecord, ...]:
    """§5 "All filters combine with AND semantics." ``search_text``
    сұрақ мәтінінде (§ ``MultipleChoiceQuestion``/``OpenResponseQuestion``/
    ``ReflectionQuestion``-тың ортақ ``prompt`` өрісі) регистрге
    сезімтал емес ішінара сәйкестік іздейді."""
    needle = search_text.strip().lower()
    result: list[QuestionRecord] = []
    for record in records:
        if experiment_id is not None and record.experiment_id != experiment_id:
            continue
        if level is not None and record.level != level:
            continue
        if status_key == _STATUS_ACTIVE_KEY and not record.is_active:
            continue
        if status_key == _STATUS_INACTIVE_KEY and record.is_active:
            continue
        if needle and needle not in record.question.prompt.lower():
            continue
        result.append(record)
    return tuple(result)


def sort_records(
    records: tuple[QuestionRecord, ...],
    experiments_by_id: dict[str, ExperimentDefinition],
) -> tuple[QuestionRecord, ...]:
    """§18 "experiment display number ascending, then level ascending,
    then stable creation/order field." Каталогта жоқ/нөмірсіз тәжірибе
    соңына ысырылады (``float("inf")``) — ешқашан exception шықпайды."""

    def sort_key(record: QuestionRecord) -> tuple[float, int, datetime]:
        experiment = experiments_by_id.get(record.experiment_id)
        display_number = (
            experiment.display_number
            if experiment is not None and experiment.display_number is not None
            else float("inf")
        )
        return (display_number, record.level, record.created_at)

    return tuple(sorted(records, key=sort_key))


def format_experiment_label(experiment: ExperimentDefinition) -> str:
    if experiment.display_number is not None:
        return f"№{experiment.display_number} {experiment.title}"
    return experiment.title


# ==========================================================================
# ҚОСУ/ӨҢДЕУ ДИАЛОГЫ
# ==========================================================================


class _OptionRow(QWidget):
    """1-деңгей сұрағының БІР жауап нұсқасы — радио (дұрыс белгісі) +
    мәтін өрісі + жою батырмасы."""

    def __init__(self, group: QButtonGroup, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.radio = QRadioButton(self)
        group.addButton(self.radio)
        self.text_edit = QLineEdit(text, self)
        # § "QPushButton{padding:12px}" әдепкі ережесінде БІР таңба
        # (мыс. "×") 28px енге сыймай, "нүктеге" дейін кесілетіні
        # эмпирикалық түрде расталды — компакт icon-батырма конвенциясы
        # (§ ThemeManager ``QPushButton[variant="icon"]``, carousel prev/
        # next-пен БІРДЕЙ, 3px padding) қолданылады.
        self.remove_button = QPushButton("×", self)
        self.remove_button.setProperty("variant", "icon")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.radio)
        layout.addWidget(self.text_edit, 1)
        layout.addWidget(self.remove_button)


class QuestionFormDialog(QDialog):
    """Сұрақ қосу/өзгерту формасы — репозиторийге ЕШБІР жазба жасамайды,
    тек ``get_values()`` арқылы енгізілген мәндерді қайтарады (§
    ``_ClassroomFormDialog``-пен БІРДЕЙ конвенция)."""

    def __init__(
        self,
        experiments: tuple[ExperimentDefinition, ...],
        existing: QuestionRecord | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._experiments = experiments
        self._existing = existing
        self.setWindowTitle("Сұрақ қосу" if existing is None else "Сұрақты өзгерту")
        self.setMinimumWidth(480)

        self._experiment_combo = QComboBox(self)
        for experiment in experiments:
            self._experiment_combo.addItem(format_experiment_label(experiment), experiment.id)

        self._level_combo = QComboBox(self)
        for level, label in _LEVEL_OPTIONS:
            self._level_combo.addItem(label, level)
        self._level_combo.currentIndexChanged.connect(self._on_level_changed)

        self._prompt_edit = QTextEdit(self)
        self._prompt_edit.setMinimumHeight(80)

        self._options_group = QButtonGroup(self)
        self._options_group.setExclusive(True)
        self._options_container = QWidget(self)
        self._options_layout = QVBoxLayout(self._options_container)
        self._options_layout.setContentsMargins(0, 0, 0, 0)
        self._add_option_button = QPushButton("+ Жауап нұсқасын қосу", self)
        self._add_option_button.clicked.connect(lambda: self._add_option_row(""))

        self._active_checkbox = QCheckBox("Белсенді сұрақ", self)
        self._active_checkbox.setChecked(True)

        form = QVBoxLayout()
        form.addWidget(QLabel("Зертханалық жұмыс:", self))
        form.addWidget(self._experiment_combo)
        form.addWidget(QLabel("Деңгей:", self))
        form.addWidget(self._level_combo)
        form.addWidget(QLabel("Сұрақ:", self))
        form.addWidget(self._prompt_edit)
        self._options_label = QLabel("Жауап нұсқалары (дұрысын белгілеңіз):", self)
        form.addWidget(self._options_label)
        form.addWidget(self._options_container)
        form.addWidget(self._add_option_button)
        form.addWidget(self._active_checkbox)

        # § QDialogButtonBox.StandardButton авто-мәтіні (Cancel/OK)
        # Кazaqша аударылмайды (§ скриншот аудитінде табылған/түзетілген
        # регрессия) — сондықтан МӘТІНІ НАҚТЫ көрсетілген жай батырмалар
        # қолданылады (§ ``confirm_delete()``-пен БІРДЕЙ тәсіл).
        cancel_button = QPushButton("Болдырмау", self)
        cancel_button.clicked.connect(self.reject)
        self._save_button = QPushButton(
            "Сақтау" if existing is None else "Өзгерістерді сақтау", self
        )
        self._save_button.setObjectName("PrimaryButton")
        self._save_button.clicked.connect(self._on_accept_clicked)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self._save_button)
        buttons.addWidget(cancel_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(buttons)

        self._populate_from_existing(existing)
        self._on_level_changed()

    # ---- Бастапқы толтыру ------------------------------------------------

    def _populate_from_existing(self, existing: QuestionRecord | None) -> None:
        if existing is None:
            self._add_option_row("")
            self._add_option_row("")
            return

        experiment_index = self._experiment_combo.findData(existing.experiment_id)
        if experiment_index >= 0:
            self._experiment_combo.setCurrentIndex(experiment_index)
        level_index = self._level_combo.findData(existing.level)
        if level_index >= 0:
            self._level_combo.setCurrentIndex(level_index)
        self._prompt_edit.setPlainText(existing.question.prompt)
        self._active_checkbox.setChecked(existing.is_active)

        if isinstance(existing.question, MultipleChoiceQuestion):
            for index, option in enumerate(existing.question.options):
                row = self._add_option_row(option)
                if index == existing.question.correct_option_index:
                    row.radio.setChecked(True)
        else:
            self._add_option_row("")
            self._add_option_row("")

    def _add_option_row(self, text: str) -> _OptionRow:
        row = _OptionRow(self._options_group, text, self._options_container)
        row.remove_button.clicked.connect(lambda: self._remove_option_row(row))
        self._options_layout.addWidget(row)
        return row

    def _remove_option_row(self, row: _OptionRow) -> None:
        if self._options_layout.count() <= _MIN_OPTIONS:
            return
        self._options_group.removeButton(row.radio)
        self._options_layout.removeWidget(row)
        row.setParent(None)
        row.deleteLater()

    def _on_level_changed(self) -> None:
        is_level1 = self._level_combo.currentData() == 1
        self._options_label.setVisible(is_level1)
        self._options_container.setVisible(is_level1)
        self._add_option_button.setVisible(is_level1)

    # ---- Валидация/растау ------------------------------------------------

    def _option_rows(self) -> list[_OptionRow]:
        return [
            self._options_layout.itemAt(i).widget()
            for i in range(self._options_layout.count())
        ]

    def _on_accept_clicked(self) -> None:
        if self._experiment_combo.currentData() is None:
            QMessageBox.warning(self, "Қате", "Зертханалық жұмысты таңдаңыз")
            return
        if not self._prompt_edit.toPlainText().strip():
            QMessageBox.warning(self, "Қате", "Сұрақ мәтіні бос болмауы керек")
            return

        if self._level_combo.currentData() == 1:
            options = [row.text_edit.text().strip() for row in self._option_rows()]
            if any(not option for option in options):
                QMessageBox.warning(self, "Қате", "Барлық жауап нұсқалары толтырылуы керек")
                return
            if len(options) < _MIN_OPTIONS:
                QMessageBox.warning(self, "Қате", f"Кемінде {_MIN_OPTIONS} жауап нұсқасы қажет")
                return
            if self._options_group.checkedButton() is None:
                QMessageBox.warning(self, "Қате", "Дұрыс жауапты белгілеңіз")
                return

        self.accept()

    # ---- Нәтиже ------------------------------------------------------------

    def get_values(self) -> tuple[str, int, QuestionContent, bool]:
        experiment_id = self._experiment_combo.currentData()
        level = self._level_combo.currentData()
        prompt = self._prompt_edit.toPlainText().strip()
        is_active = self._active_checkbox.isChecked()
        question_id = self._existing.id if self._existing is not None else str(uuid4())

        if level == 1:
            rows = self._option_rows()
            options = tuple(row.text_edit.text().strip() for row in rows)
            correct_index = next(
                (i for i, row in enumerate(rows) if row.radio.isChecked()), 0
            )
            existing_points = (
                self._existing.question.points
                if isinstance(self._existing.question if self._existing else None, MultipleChoiceQuestion)
                else 1
            )
            question: QuestionContent = MultipleChoiceQuestion(
                id=question_id, prompt=prompt, options=options,
                correct_option_index=correct_index, points=existing_points,
            )
        elif level == 2:
            question = OpenResponseQuestion(id=question_id, prompt=prompt)
        else:
            question = ReflectionQuestion(id=question_id, prompt=prompt)

        return experiment_id, level, question, is_active


# ==========================================================================
# ЖОЙУ РАСТАУ ДИАЛОГЫ
# ==========================================================================


def confirm_delete(parent: QWidget) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(_DELETE_CONFIRM_TITLE)
    box.setText(_DELETE_CONFIRM_TEXT)
    delete_button = box.addButton(_DELETE_CONFIRM_BUTTON, QMessageBox.ButtonRole.DestructiveRole)
    cancel_button = box.addButton(_DELETE_CANCEL_BUTTON, QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel_button)
    box.exec()
    return box.clickedButton() is delete_button


# ==========================================================================
# QT ВИДЖЕТ ҚАБАТЫ
# ==========================================================================


class QuestionBankPage(QWidget):
    """"Сұрақтар банкі" беті — бірінші деңгейлі sidebar тағайыны (§2:
    "← Артқа" батырмасы ЖОҚ, тақырып бірінші layout элементі)."""

    def __init__(
        self,
        question_repository: IQuestionRepository,
        module_registry: ModuleRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._question_repository = question_repository
        self._module_registry = module_registry
        self._all_records: tuple[QuestionRecord, ...] = ()
        self._experiments: tuple[ExperimentDefinition, ...] = ()
        self._experiments_by_id: dict[str, ExperimentDefinition] = {}
        self._value_labels: dict[str, QLabel] = {}

        title_label = QLabel(_PAGE_TITLE, self)
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        title_label.setFont(title_font)

        subtitle_label = QLabel(_PAGE_SUBTITLE, self)
        subtitle_label.setProperty("role", "secondary")
        subtitle_label.setWordWrap(True)

        kpi_row = QHBoxLayout()
        kpi_row.addWidget(self._build_kpi_card("total", "Барлық сұрақтар"), 1)
        kpi_row.addWidget(self._build_kpi_card("experiments", "Зертханалық жұмыстар"), 1)
        kpi_row.addWidget(self._build_kpi_card("active", "Белсенді сұрақтар"), 1)
        kpi_row.addWidget(self._build_kpi_card("average", "Орташа сұрақ саны"), 1)

        self._experiment_filter_combo = QComboBox(self)
        self._experiment_filter_combo.setMaximumWidth(_FILTER_COMBO_MAX_WIDTH)
        self._experiment_filter_combo.currentIndexChanged.connect(self._on_filters_changed)

        self._level_filter_combo = QComboBox(self)
        self._level_filter_combo.setMaximumWidth(_LEVEL_FILTER_MAX_WIDTH)
        self._level_filter_combo.addItem(_ALL_FILTER_TEXT, None)
        for level, label in _LEVEL_OPTIONS:
            self._level_filter_combo.addItem(label, level)
        self._level_filter_combo.currentIndexChanged.connect(self._on_filters_changed)

        self._status_filter_combo = QComboBox(self)
        self._status_filter_combo.setMaximumWidth(_STATUS_FILTER_MAX_WIDTH)
        self._status_filter_combo.addItem(_ALL_FILTER_TEXT, None)
        for key, label in _STATUS_FILTER_OPTIONS:
            self._status_filter_combo.addItem(label, key)
        self._status_filter_combo.currentIndexChanged.connect(self._on_filters_changed)

        self._search_edit = QLineEdit(self)
        self._search_edit.setPlaceholderText(_SEARCH_PLACEHOLDER_TEXT)
        self._search_edit.setMinimumWidth(140)
        self._search_edit.textChanged.connect(self._on_filters_changed)

        add_button = QPushButton(_ADD_QUESTION_TEXT, self)
        add_button.setObjectName("PrimaryButton")
        add_button.clicked.connect(self._on_add_question_clicked)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Зертханалық жұмыс:", self))
        filter_row.addWidget(self._experiment_filter_combo)
        filter_row.addWidget(QLabel("Деңгей:", self))
        filter_row.addWidget(self._level_filter_combo)
        filter_row.addWidget(QLabel("Күйі:", self))
        filter_row.addWidget(self._status_filter_combo)
        filter_row.addWidget(self._search_edit, 1)
        filter_row.addWidget(add_button)
        self._filter_row = filter_row

        self._empty_title_label = QLabel(self)
        self._empty_title_label.setObjectName("WorkspaceEmptyStateLabel")
        self._empty_title_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        empty_font = self._empty_title_label.font()
        empty_font.setBold(True)
        self._empty_title_label.setFont(empty_font)
        self._empty_hint_label = QLabel(self)
        self._empty_hint_label.setObjectName("WorkspaceEmptyStateLabel")
        self._empty_hint_label.setWordWrap(True)
        self._empty_hint_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._empty_add_button = QPushButton(_ADD_QUESTION_TEXT, self)
        self._empty_add_button.setObjectName("PrimaryButton")
        self._empty_add_button.clicked.connect(self._on_add_question_clicked)
        self._empty_add_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        empty_state_widget = QWidget(self)
        # § "instance-деңгейлік setStyleSheet() контейнерге қойылса, ІШКІ
        # #PrimaryButton (толық меншікті background-color/border ережесі
        # бар) баласы ӨЗ фонын ЖОҒАЛТАДЫ — эмпирикалық түрде расталған,
        # _make_background_transparent()-тің НАҚ ӨЗІ емес, оны бала
        # виджеттер (QLabel-ден басқа) бар контейнерге қолдану қатесі
        # (§ ThemeManager-дегі "QuestionBankEmptyState" глобал object-name
        # селекторы — instance stylesheet-тен ерекше, каскад бұзбайды).
        empty_state_widget.setObjectName("QuestionBankEmptyState")
        empty_state_layout = QVBoxLayout(empty_state_widget)
        empty_state_layout.setContentsMargins(0, 0, 0, 0)
        empty_state_layout.addWidget(self._empty_title_label)
        empty_state_layout.addWidget(self._empty_hint_label)
        empty_state_layout.addWidget(self._empty_add_button)
        empty_state_layout.addStretch(1)

        self._table = QTableWidget(0, len(_TABLE_HEADERS), self)
        self._table.setHorizontalHeaderLabels(list(_TABLE_HEADERS))
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(
            _QUESTION_COLUMN_INDEX, QHeaderView.ResizeMode.Stretch
        )

        results_container = QStackedWidget(self)
        results_container.setObjectName("QuestionBankTableContainer")
        results_container.addWidget(empty_state_widget)
        results_container.addWidget(self._table)
        self._results_stack = results_container
        self._empty_state_widget = empty_state_widget

        layout = QVBoxLayout(self)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addLayout(kpi_row)
        layout.addLayout(filter_row)
        layout.addWidget(results_container, 1)

        self._refresh()

    # ---- Router интерфейсі ------------------------------------------------

    def on_enter(self) -> None:
        self._refresh()

    # ---- KPI карточкалары (§4, HomeSummaryCard конвенциясы) ---------------

    def _build_kpi_card(self, key: str, label: str) -> QWidget:
        card = QFrame(self)
        card.setObjectName("HomeSummaryCard")

        value_label = QLabel(_NO_VALUE_TEXT, card)
        value_label.setProperty("role", "cardValue")
        _make_background_transparent(value_label)
        self._value_labels[key] = value_label

        caption_label = QLabel(label, card)
        caption_label.setProperty("role", "cardLabel")
        _make_background_transparent(caption_label)

        card_layout = QVBoxLayout(card)
        card_layout.addWidget(value_label)
        card_layout.addWidget(caption_label)
        return card

    # ---- Дерек жаңарту -------------------------------------------------------

    def _refresh(self) -> None:
        self._all_records = self._question_repository.list_all(include_archived=True)
        self._experiments = iter_catalog_experiments(self._module_registry)
        self._experiments_by_id = {e.id: e for e in self._experiments}

        kpis = compute_kpis(self._all_records)
        self._value_labels["total"].setText(kpis.total_text)
        self._value_labels["experiments"].setText(kpis.experiments_with_questions_text)
        self._value_labels["active"].setText(kpis.active_text)
        self._value_labels["average"].setText(kpis.average_text)

        self._populate_experiment_filter()
        self._render_table()

    def _populate_experiment_filter(self) -> None:
        current = self._experiment_filter_combo.currentData()
        self._experiment_filter_combo.blockSignals(True)
        self._experiment_filter_combo.clear()
        self._experiment_filter_combo.addItem(_ALL_FILTER_TEXT, None)
        active_counts: dict[str, int] = {}
        for record in self._all_records:
            if record.is_active:
                active_counts[record.experiment_id] = active_counts.get(record.experiment_id, 0) + 1
        for experiment in self._experiments:
            count = active_counts.get(experiment.id, 0)
            label = f"{format_experiment_label(experiment)} ({count})"
            self._experiment_filter_combo.addItem(label, experiment.id)
        restored = self._experiment_filter_combo.findData(current)
        self._experiment_filter_combo.setCurrentIndex(restored if restored >= 0 else 0)
        self._experiment_filter_combo.blockSignals(False)

    def _on_filters_changed(self) -> None:
        self._render_table()

    def _current_filters(self) -> tuple[str | None, int | None, str | None, str]:
        return (
            self._experiment_filter_combo.currentData(),
            self._level_filter_combo.currentData(),
            self._status_filter_combo.currentData(),
            self._search_edit.text(),
        )

    def _render_table(self) -> None:
        experiment_id, level, status_key, search_text = self._current_filters()
        filtered = filter_records(self._all_records, experiment_id, level, status_key, search_text)
        rows = sort_records(filtered, self._experiments_by_id)

        has_any_records = len(self._all_records) > 0
        has_visible_rows = len(rows) > 0

        if not has_any_records:
            self._empty_title_label.setText(_EMPTY_REPOSITORY_TITLE)
            self._empty_hint_label.setText(_EMPTY_REPOSITORY_HINT)
            self._empty_add_button.setVisible(True)
        elif not has_visible_rows:
            self._empty_title_label.setText(_EMPTY_FILTERED_TITLE)
            self._empty_hint_label.setText(_EMPTY_FILTERED_HINT)
            self._empty_add_button.setVisible(False)
        self._results_stack.setCurrentWidget(self._table if has_visible_rows else self._results_stack.widget(0))

        # § results_page.py-дегі ДӘЛ СОЛ "cellWidget-тер setRowCount(0)-мен
        # көрінбей де, объект ағашында қалып қоятын" bag түзетуімен БІРДЕЙ —
        # ескі әрекет виджеттерін ЖОЛДАР қысқартылмас бұрын анық бөліп алу.
        for row in range(self._table.rowCount()):
            old_widget = self._table.cellWidget(row, _ACTION_COLUMN_INDEX)
            if old_widget is not None:
                old_widget.setParent(None)
                old_widget.deleteLater()
        self._table.setRowCount(0)
        self._table.setRowCount(len(rows))
        for row_index, record in enumerate(rows):
            self._populate_row(row_index, record)
        if has_visible_rows:
            # § results_page.py-дегі ДӘЛ СОЛ рет: алдымен мазмұнға сай
            # авто-өлшеу (§ "Зертханалық жұмыс"/"Деңгей"/"Күйі" бағандары
            # ӨЗ тақырып мәтінінен кесілмеуі үшін), содан кейін ғана
            # stretch/нақты ені бекітілген бағандар үстіне жазылады.
            self._table.resizeColumnsToContents()
            self._table.setColumnWidth(0, 40)
            self._table.horizontalHeader().setSectionResizeMode(
                _QUESTION_COLUMN_INDEX, QHeaderView.ResizeMode.Stretch
            )
            self._table.setColumnWidth(_ACTION_COLUMN_INDEX, 150)

    def _populate_row(self, row_index: int, record: QuestionRecord) -> None:
        experiment = self._experiments_by_id.get(record.experiment_id)
        experiment_text = format_experiment_label(experiment) if experiment is not None else record.experiment_id

        values = (str(row_index + 1), experiment_text)
        for column, text in enumerate(values):
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row_index, column, item)

        level_item = QTableWidgetItem(_LEVEL_TEXT[record.level])
        level_item.setFlags(level_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        level_color = _LEVEL_COLOR.get(record.level)
        if level_color is not None:
            level_item.setForeground(QColor(level_color))
        self._table.setItem(row_index, 2, level_item)

        prompt_item = QTableWidgetItem(record.question.prompt)
        prompt_item.setFlags(prompt_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._table.setItem(row_index, _QUESTION_COLUMN_INDEX, prompt_item)

        status_item = QTableWidgetItem(_STATUS_TEXT[record.is_active])
        status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        status_item.setForeground(QColor(_STATUS_COLOR[record.is_active]))
        self._table.setItem(row_index, 4, status_item)

        action_widget = QWidget(self._table)
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(0, 0, 0, 0)
        edit_button = QPushButton(_EDIT_TEXT, action_widget)
        edit_button.clicked.connect(lambda _checked=False, r=record: self._on_edit_clicked(r))
        delete_button = QPushButton(_DELETE_TEXT, action_widget)
        delete_button.clicked.connect(lambda _checked=False, r=record: self._on_delete_clicked(r))
        action_layout.addWidget(edit_button)
        action_layout.addWidget(delete_button)
        self._table.setCellWidget(row_index, _ACTION_COLUMN_INDEX, action_widget)

    # ---- Қосу/Өңдеу/Өшіру ---------------------------------------------------

    def _on_add_question_clicked(self) -> None:
        if not self._experiments:
            QMessageBox.warning(
                self, "Қате", "Алдымен зертханалық жұмыс каталогында тәжірибе болуы керек"
            )
            return
        dialog = QuestionFormDialog(self._experiments, existing=None, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        experiment_id, level, question, is_active = dialog.get_values()
        self._question_repository.create(
            QuestionRecord(
                id=question.id, experiment_id=experiment_id, level=level,
                question=question, is_active=is_active, created_at=datetime.now(timezone.utc),
            ),
            UserRole.TEACHER,
        )
        self._refresh()

    def _on_edit_clicked(self, record: QuestionRecord) -> None:
        dialog = QuestionFormDialog(self._experiments, existing=record, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        experiment_id, level, question, is_active = dialog.get_values()
        self._question_repository.update(
            QuestionRecord(
                id=record.id, experiment_id=experiment_id, level=level,
                question=question, is_active=is_active, created_at=record.created_at,
            ),
            UserRole.TEACHER,
        )
        self._refresh()

    def _on_delete_clicked(self, record: QuestionRecord) -> None:
        if not confirm_delete(self):
            return
        self._question_repository.archive(record.id, UserRole.TEACHER, archived=True)
        self._refresh()
