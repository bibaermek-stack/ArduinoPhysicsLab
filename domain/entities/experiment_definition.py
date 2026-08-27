"""ExperimentDefinition — бір зертхана жұмысының конфигурациясы
(аты, қажетті арналар, формула, график баптаулары).
"""

from dataclasses import dataclass, field

from domain.entities.experiment_assessment import ExperimentAssessmentDefinition
from domain.entities.sensor_channel import SensorChannel
from domain.services.graph_analysis import DERIVED_ANALYSIS_POWER_ENERGY

_VALID_DERIVED_ANALYSES = (DERIVED_ANALYSIS_POWER_ENERGY,)


@dataclass(frozen=True)
class RateOfChangeConfig:
    """Phase 34 §3/§11: уақыттық график арнасы үшін физикалық мағыналы
    туынды (dY/dt) конфигурациясы (мыс. dT/dt → "қызу жылдамдығы").
    Тек таңдалған аралық (region) үшін есептеледі — толық ағын
    ЕШҚАШАН нүкте-нүктелеп сандық дифференциалданбайды (шу күшейеді).
    """

    channel_key: str
    symbol: str
    display_name: str
    unit: str


_GUIDE_STRING_TUPLE_FIELDS = (
    "objective",
    "equipment",
    "formulas",
    "procedure",
    "safety",
    "control_questions",
)


@dataclass(frozen=True)
class ExperimentGuide:
    """Phase 35: бір зертхана жұмысының толық нұсқаулығы (мақсаты,
    жабдық, теория, формулалар, орындау тәртібі, қауіпсіздік,
    бақылау сұрақтары) — ``ExperimentWorkspacePage``-тегі "📘 Нұсқаулық"
    диалогының жалғыз дерек көзі.

    Барлық tuple өрісі ӘДЕПКІ БОЙЫНША бос — тек мазмұны бар секция ғана
    UI-де көрсетіледі (§6: "Do NOT show an empty heading/card"), бос
    ``()``/``""`` толық жарамды конфигурация. Нөмірлеу (``procedure``/
    ``control_questions``) жолдардың ІШІНДЕ САҚТАЛМАЙДЫ — UI рендер
    кезінде ``f"{index+1}. "`` префиксін өзі қосады (§8/§9).
    """

    objective: tuple[str, ...] = field(default_factory=tuple)
    equipment: tuple[str, ...] = field(default_factory=tuple)
    theory: str = ""
    formulas: tuple[str, ...] = field(default_factory=tuple)
    procedure: tuple[str, ...] = field(default_factory=tuple)
    safety: tuple[str, ...] = field(default_factory=tuple)
    control_questions: tuple[str, ...] = field(default_factory=tuple)

    def validate(self) -> list[str]:
        """Конфигурацияның ішкі қайшылықтарын тексереді (dataclass
        өрістердің типін ЕШҚАШАН орындау уақытында мәжбүрлемейді,
        сондықтан бұл жерде НАҚТЫ тексеріледі — қате тип/малформed
        коллекция орнына түсінікті қате хабарламасы, exception емес).
        """
        errors: list[str] = []
        for field_name in _GUIDE_STRING_TUPLE_FIELDS:
            value = getattr(self, field_name)
            if not isinstance(value, tuple) or not all(isinstance(item, str) for item in value):
                errors.append(f"ExperimentGuide.{field_name} тек str tuple болуы тиіс")
        if not isinstance(self.theory, str):
            errors.append("ExperimentGuide.theory тек str болуы тиіс")
        return errors


@dataclass(frozen=True)
class ExperimentReport:
    """Phase 36: зертханалық есеп диалогының КОНФИГУРАЦИЯ бөлігі ғана
    (``ExperimentReportDialog``-тың дерек көзі).

    Әдейі МИНИМАЛ: мақсат/жабдық ``ExperimentGuide``-тен ҚАЙТА
    ПАЙДАЛАНЫЛАДЫ (осында ЕШҚАШАН қайталанбайды), ал өлшенген
    статистика/график/есептелген шамалар толығымен
    ``domain.services.experiment_report_data.build_experiment_report_data()``
    арқылы сессиядан ӘР РЕТ ЖАҢАДАН есептеледі ("no fake calculations,
    no duplicated logic"). Бұл дата тек диалог тақырыбы/қорытынды
    жолының үстіндегі қосымша нұсқаулықты сақтайды.
    """

    title: str = "Зертханалық есеп"
    conclusion_prompt: str = ""

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not isinstance(self.title, str):
            errors.append("ExperimentReport.title тек str болуы тиіс")
        if not isinstance(self.conclusion_prompt, str):
            errors.append("ExperimentReport.conclusion_prompt тек str болуы тиіс")
        return errors


@dataclass(frozen=True)
class ExperimentDiagram:
    """Phase 36.1: "📐 Схема" диалогының дерек көзі — тәжірибенің НАҚТЫ
    (пайдаланушы дайындаған, Fritzing-тәрізді) қосылым суретінің файл
    жолы мен міндетті емес түсінік жолы.

    Сурет ӨЗІ кодта ЕШҚАШАН қайта салынбайды/generate етілмейді — тек
    дайын PNG файлдың жолы сақталады (``ExperimentDiagramDialog`` оны
    ``QPixmap``-пен жүктейді). Тек ``image_path``/``caption`` сақтайды —
    диалог тақырыбы/тұрақты "Қосылу схемасы" subtitle-ы диалогтың өзінде
    (experiment title-мен бірге), сондықтан бұл жерде қайталанбайды.
    """

    image_path: str
    caption: str = ""

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not isinstance(self.image_path, str) or not self.image_path:
            errors.append("ExperimentDiagram.image_path тек бос емес str болуы тиіс")
        if not isinstance(self.caption, str):
            errors.append("ExperimentDiagram.caption тек str болуы тиіс")
        return errors


@dataclass(frozen=True)
class ExperimentDefinition:
    id: str
    title: str
    description: str
    required_channels: tuple[SensorChannel, ...] = field(default_factory=tuple)
    derived_channels: tuple[SensorChannel, ...] = field(default_factory=tuple)
    graph_x_channel: str | None = None
    graph_y_channels: tuple[str, ...] = field(default_factory=tuple)
    formulas: dict[str, str] = field(default_factory=dict)
    display_channels: tuple[str, ...] = field(default_factory=tuple)
    # required_channels-тен бөлек мағына: бұл — ДЕРЕКТЕР кілттері емес,
    # ФИЗИКАЛЫҚ құрылғы түрлері (domain.constants.sensor_types), тәжірибені
    # орындау үшін қосылып тұруы тиіс (мыс. Ohm's Law → ("VOLTAGE","CURRENT")).
    # UI осыны "readiness" checklist-ке, MultiSensorExperimentCoordinator
    # port-pipeline санына қолданады.
    required_sensor_types: tuple[str, ...] = field(default_factory=tuple)
    # ---- LiveGraphWidget presentation конфигурациясы (V1: Vernier тәрізді
    # scatter+fit графигі, тек Ohm's Law-да іске қосылады) ----
    # Әдепкі мәндер бұрынғы мінез-құлықты сақтайды: барлық ескі тәжірибе
    # (connect_points=True) сызықпен қосылған график ретінде қала береді.
    graph_connect_points: bool = True
    graph_show_fit: bool = False
    graph_title: str | None = None
    graph_x_label: str | None = None
    graph_y_label: str | None = None
    graph_dedup_x_tolerance: float = 0.0
    graph_dedup_y_tolerance: float = 0.0
    # Fit нәтижесінің toolbar мәтінінде қолданылатын атау/бірлік (мыс. Ohm's
    # Law-да slope физикалық кедергі болғандықтан "R"/"Ω" қолданылады).
    graph_fit_result_prefix: str = "slope"
    graph_fit_unit: str | None = None
    # ---- V2: Vernier тәрізді manual point capture (тек Ohm's Law) ----
    # "automatic" — raw 10Hz Measurement ағыны графикке тікелей түседі (V1
    # мінез-құлқы, барлық ескі тәжірибе). "manual" — тек пайдаланушы "Нүктені
    # сақтау" батырмасын басқанда, соңғы N тұрақты үлгінің орташасынан бір
    # нүкте қосылады (transient/шулы аралық мәндер fit-ке кірмейді).
    graph_capture_mode: str = "automatic"
    graph_capture_sample_count: int = 10
    graph_capture_x_tolerance: float = 0.002
    graph_capture_y_tolerance: float = 0.02
    # Linear fit теңдеуінде көрсетілетін айнымалы әріптер (мыс. "U = m·I + b").
    graph_fit_x_symbol: str = "X"
    graph_fit_y_symbol: str = "Y"
    # ---- V3: dual stacked time-series graph (мыс. "Электр тізбегін
    # құрастыру және ток күшін өлшеу") ----
    # True болса, LiveGraphWidget әр graph_y_channels кілті үшін ӨЗ
    # PlotWidget-ін (ортақ, синхрондалған X осімен) салады — voltage/current
    # секілді әртүрлі бірлік/диапазонды шамаларды бір Y scale-ге қыспау үшін.
    # Тек уақыттық режимде (graph_x_channel=None) және fit/manual capture-сыз
    # мағыналы.
    graph_stacked: bool = False
    graph_stacked_titles: dict[str, str] = field(default_factory=dict)
    graph_stacked_y_labels: dict[str, str] = field(default_factory=dict)
    # ---- Phase 33B: physics-aware derived analysis (§10) ----
    # Бос жол — ешбір туынды талдау (Қуат/Жұмыс секілді) көрсетілмейді.
    # МӘНДІ болса, LiveGraphWidget осы жалпы config мәнін оқиды — эксперимент
    # ID-ге ЕШБІР hardcoded тәуелділік ЖОҚ (болашақ Жылу/Магнетизм/Оптика
    # модульдері де осы конфигурация нүктесін қайта пайдалана алады).
    graph_derived_analysis: str = ""
    # ---- V3: optional (әдепкі жасырын) display арналар (мыс. Қуат) ----
    # display_channels-тен бөлек мағына: readout/table-де БАР, бірақ
    # пайдаланушы toggle батырмасымен көрсету/жасыруы мүмкін. Backend
    # есептеуі (CalculationEngine) мен деректер жинау (Measurement/
    # ExperimentSession/export) бұған тәуелсіз — тек presentation.
    optional_display_channels: tuple[str, ...] = field(default_factory=tuple)
    optional_display_show_label: str = "Қосымша мәндерді көрсету"
    optional_display_hide_label: str = "Қосымша мәндерді жасыру"
    # ---- Phase 36.1: "📐 Схема" — НАҚТЫ қосылым суреті (Guide/Report-пен
    # БІРДЕЙ backward-compatibility механизмі) ----
    # None — бұл тәжірибеге әлі диаграмма конфигурацияланбаған (ескі/жаңа
    # кез келген ExperimentDefinition сынағы ӨЗГЕРІССІЗ жұмыс істейді).
    # ExperimentWorkspacePage "📐 Схема" батырмасын тек diagram is not None
    # болғанда ғана көрсетеді.
    diagram: ExperimentDiagram | None = None
    # ---- V5: Laboratory Catalog — каталогтық нөмір/іске асыру күйі ----
    # display_number — тәжірибенің каталогтағы authoritative нөмірі (1..12),
    # ішкі ``id``-ден және модуль tuple-ындағы ретінен ТӘУЕЛСІЗ (id тұрақты
    # қалады, дисплей нөмірі UI/каталог метадеректері ғана).
    display_number: int | None = None
    # is_implemented=False — тәжірибе әлі каталогта ғана (нақты workspace/
    # sensor pipeline жоқ). UI мұны "Жоспарланған" деп көрсетіп, таңдауды
    # блоктайды; validate_configuration()-ге қатысы жоқ (ол өлшеу-wiring
    # дұрыстығын тексереді, каталог күйін емес).
    is_implemented: bool = True
    # ---- Phase 34: physics-aware measurement/analysis instrument ----
    # A/B екі нүктелік Δ өлшеу құралы (toolbar батырмасы) — тек осы
    # мәні True тәжірибелерде көрінеді (мыс. тізбек бөлігі үшін
    # тәуелділікті зерттеу, электр тізбегін құрастыру және ток күшін
    # өлшеу тәжірибелері).
    graph_allow_delta_measurement: bool = False
    # Уақыттық графиктегі әр арна үшін физикалық мағыналы rate-of-change
    # (dY/dt) — тек region таңдалғанда есептеледі (§3). Бос tuple —
    # ешбір rate-of-change көрсетілмейді (әдепкі, ескі мінез-құлық).
    graph_rate_of_change: tuple[RateOfChangeConfig, ...] = field(default_factory=tuple)
    # graph_fit_result_prefix (мыс. "R") қасындағы қосымша қазақша атау
    # (мыс. "Кедергі") — таза косметикалық, symbol/formula ауыстырылмайды.
    graph_fit_display_name: str | None = None
    # ---- Phase 35: Experiment Guide / Laboratory Instructions ----
    # None — бұл тәжірибеге әлі нұсқаулық жазылмаған (ескі/жаңа кез
    # келген ExperimentDefinition сынағы ӨЗГЕРІССІЗ жұмыс істейді —
    # backward compatibility осы әдепкі мәннен тегін келеді).
    # ExperimentWorkspacePage "📘 Нұсқаулық" батырмасын тек guide is not
    # None болғанда ғана көрсетеді.
    guide: ExperimentGuide | None = None
    # ---- Phase 36: Laboratory Report architecture ----
    # None — бұл тәжірибеге әлі есеп конфигурацияланбаған (backward
    # compatibility ``guide``-мен БІРДЕЙ механизм). ExperimentWorkspacePage
    # "📄 Есеп" батырмасын тек report is not None болғанда көрсетеді.
    report: ExperimentReport | None = None
    # ---- Phase 39A: үш деңгейлі кері байланыс/бағалау ----
    # None — бұл тәжірибеге әлі бағалау конфигурацияланбаған (guide/
    # report-пен БІРДЕЙ backward-compatibility механизмі). "Кері
    # байланысты бастау" әрекеті тек assessment is not None болғанда
    # көрінеді, workflow-дың 6-қадамы (Кері байланыс) None болса дереу
    # "✓" болып көрсетіледі.
    assessment: ExperimentAssessmentDefinition | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id бос болмауы керек")
        if not self.title:
            raise ValueError("title бос болмауы керек")

    def _all_channel_keys(self) -> set[str]:
        return {channel.key for channel in (*self.required_channels, *self.derived_channels)}

    def validate_configuration(self) -> list[str]:
        """Конфигурацияның ішкі қайшылықтарын тексеріп, қате хабарламаларының
        тізімін қайтарады (ешбір exception шығармайды).
        """
        errors: list[str] = []
        all_keys = self._all_channel_keys()

        if not self.required_channels:
            errors.append("required_channels бос болмауы тиіс")

        seen_keys: set[str] = set()
        for channel in (*self.required_channels, *self.derived_channels):
            if channel.key in seen_keys:
                errors.append(f"'{channel.key}' арнасы бірнеше рет анықталған")
            seen_keys.add(channel.key)

        if self.graph_x_channel is not None and self.graph_x_channel not in all_keys:
            errors.append(
                f"graph_x_channel '{self.graph_x_channel}' анықталған арналар арасында жоқ"
            )

        for channel_key in self.graph_y_channels:
            if channel_key not in all_keys:
                errors.append(
                    f"graph_y_channels ішіндегі '{channel_key}' анықталған арналар арасында жоқ"
                )

        derived_keys = {channel.key for channel in self.derived_channels}
        for formula_key in self.formulas:
            if formula_key not in derived_keys:
                errors.append(
                    f"formulas ішіндегі '{formula_key}' derived_channels арасында жоқ"
                )

        for channel_key in self.display_channels:
            if channel_key not in all_keys:
                errors.append(
                    f"display_channels ішіндегі '{channel_key}' анықталған арналар арасында жоқ"
                )

        seen_sensor_types: set[str] = set()
        for sensor_type in self.required_sensor_types:
            if sensor_type in seen_sensor_types:
                errors.append(
                    f"required_sensor_types ішінде '{sensor_type}' бірнеше рет қайталанды"
                )
            seen_sensor_types.add(sensor_type)

        if self.graph_dedup_x_tolerance < 0:
            errors.append("graph_dedup_x_tolerance теріс бола алмайды")
        if self.graph_dedup_y_tolerance < 0:
            errors.append("graph_dedup_y_tolerance теріс бола алмайды")

        if self.graph_show_fit and self.graph_x_channel is None:
            errors.append("graph_show_fit тек X-Y режимінде (graph_x_channel берілгенде) қолданылады")

        if self.graph_capture_mode not in ("automatic", "manual"):
            errors.append("graph_capture_mode тек 'automatic' немесе 'manual' бола алады")
        if self.graph_capture_sample_count <= 0:
            errors.append("graph_capture_sample_count оң сан болуы тиіс")
        if self.graph_capture_x_tolerance < 0:
            errors.append("graph_capture_x_tolerance теріс бола алмайды")
        if self.graph_capture_y_tolerance < 0:
            errors.append("graph_capture_y_tolerance теріс бола алмайды")
        if self.graph_capture_mode == "manual" and self.graph_x_channel is None:
            errors.append("graph_capture_mode='manual' тек X-Y режимінде (graph_x_channel берілгенде) қолданылады")

        if self.graph_stacked and self.graph_x_channel is not None:
            errors.append("graph_stacked тек уақыттық режимде (graph_x_channel=None) қолданылады")
        if self.graph_stacked and (self.graph_show_fit or self.graph_capture_mode == "manual"):
            errors.append("graph_stacked fit/manual capture режимдерімен бірге қолданылмайды")

        if self.graph_derived_analysis and self.graph_derived_analysis not in _VALID_DERIVED_ANALYSES:
            errors.append(
                f"graph_derived_analysis '{self.graph_derived_analysis}' белгісіз мән "
                f"(рұқсат етілген: {', '.join(_VALID_DERIVED_ANALYSES)})"
            )
        if self.graph_derived_analysis == DERIVED_ANALYSIS_POWER_ENERGY and "power" not in all_keys:
            errors.append(
                "graph_derived_analysis='power_energy' үшін 'power' арнасы анықталуы тиіс"
            )

        optional_keys = set(self.optional_display_channels)
        for channel_key in optional_keys:
            if channel_key not in all_keys:
                errors.append(
                    f"optional_display_channels ішіндегі '{channel_key}' анықталған арналар арасында жоқ"
                )
        if optional_keys & set(self.display_channels):
            errors.append("optional_display_channels мен display_channels қабаттаспауы тиіс")

        if self.graph_rate_of_change and self.graph_x_channel is not None:
            errors.append(
                "graph_rate_of_change тек уақыттық режимде (graph_x_channel=None) қолданылады"
            )
        seen_rate_keys: set[str] = set()
        for rate_config in self.graph_rate_of_change:
            if rate_config.channel_key in seen_rate_keys:
                errors.append(
                    f"graph_rate_of_change ішінде '{rate_config.channel_key}' бірнеше рет қайталанды"
                )
            seen_rate_keys.add(rate_config.channel_key)
            if rate_config.channel_key not in all_keys:
                errors.append(
                    f"graph_rate_of_change ішіндегі '{rate_config.channel_key}' анықталған "
                    "арналар арасында жоқ"
                )
            elif rate_config.channel_key not in self.graph_y_channels:
                errors.append(
                    f"graph_rate_of_change ішіндегі '{rate_config.channel_key}' "
                    "graph_y_channels арасында жоқ"
                )

        # Phase 35: guide=None (әдепкі, ескі тәжірибелер) толық жарамды —
        # тек НАҚТЫ конфигурацияланған guide ішкі қайшылықтары тексеріледі.
        if self.guide is not None:
            errors.extend(self.guide.validate())

        # Phase 36: report=None да дәл сол себеппен толық жарамды.
        if self.report is not None:
            errors.extend(self.report.validate())

        # Phase 36.1: diagram=None да дәл сол себеппен толық жарамды.
        if self.diagram is not None:
            errors.extend(self.diagram.validate())

        # Phase 39A: assessment=None да дәл сол себеппен толық жарамды.
        if self.assessment is not None:
            errors.extend(self.assessment.validate())

        return errors

    def requires_multiple_sensors(self) -> bool:
        """Тәжірибені орындау үшін бірден көп физикалық сенсор (COM-порт)
        бір мезгілде қосылып тұруы тиіс пе — соны қайтарады.
        """
        return len(self.required_sensor_types) > 1

    @property
    def graph_mode(self) -> str:
        """Графиктің режимі: ``graph_x_channel`` берілсе "xy" (X-Y тәуелділік),
        әйтпесе "time" (уақыттық режим). ``LiveGraphWidget.configure_channels()``-тегі
        ``x_channel is None`` шартымен бірдей логика — қосымша сақталған күй емес,
        тек оқуға ыңғайлы есеп (computed) property.
        """
        return "xy" if self.graph_x_channel is not None else "time"

    def get_display_channels(self) -> tuple[SensorChannel, ...]:
        """UI-де көрсетілетін арналардың рет-ретімен tuple-ын қайтарады.

        ``display_channels`` анық көрсетілсе, дәл сол ретпен қолданылады
        (required_channels/derived_channels ішінен сәйкес ``SensorChannel``
        іздеп табады; сәйкес келмесе, key-ді өзін label/unit-сіз "fallback"
        ретінде қолданады — UI ешқашан белгісіз кілттен құламайды).
        Көрсетілмесе (әдепкі бос tuple), required_channels + derived_channels
        ретімен қайтарады.
        """
        channels_by_key = {
            channel.key: channel for channel in (*self.required_channels, *self.derived_channels)
        }

        if not self.display_channels:
            return (*self.required_channels, *self.derived_channels)

        return tuple(
            channels_by_key.get(key)
            or SensorChannel(key=key, display_name=key, unit="", required=False)
            for key in self.display_channels
        )

    def get_optional_display_channels(self) -> tuple[SensorChannel, ...]:
        """``get_display_channels()``-пен бірдей resolve-логикасы, бірақ
        ``optional_display_channels`` тізімі бойынша — бұлар UI-де
        әдепкі жасырын, тек пайдаланушы toggle-мен көрсете алатын
        қосымша арналар (мыс. Қуат). Backend есептеу/деректер жинауға
        (CalculationEngine/Measurement/export) ешбір қатысы жоқ.
        """
        channels_by_key = {
            channel.key: channel for channel in (*self.required_channels, *self.derived_channels)
        }
        return tuple(
            channels_by_key.get(key)
            or SensorChannel(key=key, display_name=key, unit="", required=False)
            for key in self.optional_display_channels
        )
