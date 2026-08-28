"""ElectricityModule және experiments_config үшін юнит-тесттер."""

import os

from domain.interfaces.i_physics_module import IPhysicsModule
from modules.electricity.experiments_config import (
    CURRENT_VOLTAGE_EXPERIMENT,
    CURRENT_WORK_POWER_EXPERIMENT,
    ELECTRICITY_EXPERIMENTS,
    METAL_RESISTANCE_TEMPERATURE_EXPERIMENT,
    OHMS_LAW_EXPERIMENT,
    PARALLEL_CONNECTION_EXPERIMENT,
    SERIES_CONNECTION_EXPERIMENT,
    TEMPERATURE_CHANNEL,
)
from modules.electricity.module import ElectricityModule


def test_electricity_module_implements_interface() -> None:
    module = ElectricityModule()

    assert isinstance(module, IPhysicsModule)


def test_electricity_module_returns_name() -> None:
    module = ElectricityModule()

    assert module.get_name() == "Электр құбылыстары"


def test_electricity_module_returns_six_experiments() -> None:
    # Каталогта 6 электр тәжірибесі бар; температура firmware жоқ
    # болғандықтан metal-resistance-temperature is_implemented=False.
    module = ElectricityModule()

    experiments = module.get_experiments()

    assert len(experiments) == 6
    assert experiments == ELECTRICITY_EXPERIMENTS


def test_implemented_experiment_internal_ids_unchanged() -> None:
    # Catalog order correction: display_number/order өзгерді, бірақ жұмыс
    # істеп тұрған pipeline-дердің internal ID-і мүлде өзгермеуі тиіс.
    implemented_ids = {e.id for e in ELECTRICITY_EXPERIMENTS if e.is_implemented}
    assert implemented_ids == {
        "current-voltage",
        "series-connection",
        "parallel-connection",
        "current-work-power",
        "ohms-law",
    }


def test_experiment_ids_are_unique() -> None:
    ids = [experiment.id for experiment in ELECTRICITY_EXPERIMENTS]

    assert len(ids) == len(set(ids))


def test_all_implemented_experiments_have_valid_configuration() -> None:
    # validate_configuration() өлшеу-wiring дұрыстығын тексереді — бұл
    # тек НАҚТЫ орындалатын тәжірибелерге қатысты. Каталог-қана жазба
    # (is_implemented=False) ешқашан workspace ашпайды, сондықтан
    # required_channels=() болуы заңды, "қате" емес.
    for experiment in ELECTRICITY_EXPERIMENTS:
        if not experiment.is_implemented:
            continue
        assert experiment.validate_configuration() == []


# ---- Әр тәжірибенің дұрыс display channel реті (2-бөлім спецификациясы) ---


def test_current_voltage_display_channel_order() -> None:
    # V3: Power ЕНДІ optional (әдепкі жасырын) — display_channels тек U,I.
    keys = [c.key for c in CURRENT_VOLTAGE_EXPERIMENT.get_display_channels()]
    assert keys == ["voltage", "current"]
    optional_keys = [c.key for c in CURRENT_VOLTAGE_EXPERIMENT.get_optional_display_channels()]
    assert optional_keys == ["power"]


def test_ohms_law_display_channel_order() -> None:
    keys = [c.key for c in OHMS_LAW_EXPERIMENT.get_display_channels()]
    assert keys == ["voltage", "current", "resistance"]


def test_series_connection_display_channel_order() -> None:
    keys = [c.key for c in SERIES_CONNECTION_EXPERIMENT.get_display_channels()]
    assert keys == ["voltage", "current", "resistance", "power"]


def test_parallel_connection_display_channel_order() -> None:
    keys = [c.key for c in PARALLEL_CONNECTION_EXPERIMENT.get_display_channels()]
    assert keys == ["voltage", "current", "resistance", "power"]


def test_current_work_power_display_channel_order() -> None:
    keys = [c.key for c in CURRENT_WORK_POWER_EXPERIMENT.get_display_channels()]
    assert keys == ["time", "power", "work"]


def test_current_work_power_still_requires_voltage_and_current_for_calculation() -> None:
    # voltage/current display-де көрсетілмесе де, power=U×I есептеу үшін
    # required_channels-те қалуы керек (backend өзгермегенін растайды).
    required_keys = {c.key for c in CURRENT_WORK_POWER_EXPERIMENT.required_channels}
    assert {"voltage", "current", "time"} == required_keys


# ---- Multi-device: required_sensor_types + CURRENT_CHANNEL.required=True -


def test_channel_constants_are_reexported_from_experiments_config() -> None:
    from modules.electricity import channels
    from modules.electricity.experiments_config import CURRENT_CHANNEL, VOLTAGE_CHANNEL

    assert VOLTAGE_CHANNEL is channels.VOLTAGE_CHANNEL
    assert CURRENT_CHANNEL is channels.CURRENT_CHANNEL


def test_current_channel_is_required_again() -> None:
    # ChannelAggregator толық жиынтықты бергеннен кейін ғана DataValidator
    # шақырылады, сондықтан партиалды (voltage-only) пакет ешқашан
    # DataValidator-ге жетпейді — current-ті қайта required=True етуге
    # болады (V1 hardware-test workaround-ы енді қажет емес).
    from modules.electricity.experiments_config import CURRENT_CHANNEL

    assert CURRENT_CHANNEL.required is True


def test_all_implemented_experiments_require_voltage_and_current_sensors() -> None:
    # Phase 38B: metal-resistance-temperature ЕНДІ толық іске асырылған
    # және қосымша TEMPERATURE сенсорын да талап етеді (әлі нақты
    # firmware-і жоқ — "hardware adapter белсенді емес" күйі), сондықтан
    # VOLTAGE/CURRENT ішкі жиын ретінде тексеріледі, дәл теңдік емес.
    for experiment in ELECTRICITY_EXPERIMENTS:
        if not experiment.is_implemented:
            continue
        assert "VOLTAGE" in experiment.required_sensor_types
        assert "CURRENT" in experiment.required_sensor_types
        assert experiment.requires_multiple_sensors() is True


def test_metal_resistance_temperature_additionally_requires_temperature_sensor() -> None:
    assert METAL_RESISTANCE_TEMPERATURE_EXPERIMENT.required_sensor_types == (
        "VOLTAGE",
        "CURRENT",
        "TEMPERATURE",
    )


# ---- Ohm's Law: Vernier тәрізді scatter+fit график конфигурациясы ---------


def test_ohms_law_graph_uses_current_on_x_and_voltage_on_y() -> None:
    assert OHMS_LAW_EXPERIMENT.graph_x_channel == "current"
    assert OHMS_LAW_EXPERIMENT.graph_y_channels == ("voltage",)
    assert OHMS_LAW_EXPERIMENT.graph_mode == "xy"


def test_ohms_law_graph_is_scatter_with_fit() -> None:
    assert OHMS_LAW_EXPERIMENT.graph_connect_points is False
    assert OHMS_LAW_EXPERIMENT.graph_show_fit is True
    assert OHMS_LAW_EXPERIMENT.graph_fit_result_prefix == "R"
    assert OHMS_LAW_EXPERIMENT.graph_fit_unit == "Ω"


def test_ohms_law_graph_labels_and_title() -> None:
    assert OHMS_LAW_EXPERIMENT.graph_title == "Кернеудің ток күшіне тәуелділігі"
    assert OHMS_LAW_EXPERIMENT.graph_x_label == "Ток, I"
    assert OHMS_LAW_EXPERIMENT.graph_y_label == "Кернеу, U"


def test_ohms_law_graph_has_positive_dedup_tolerances() -> None:
    assert OHMS_LAW_EXPERIMENT.graph_dedup_x_tolerance > 0
    assert OHMS_LAW_EXPERIMENT.graph_dedup_y_tolerance > 0


def test_other_experiments_keep_default_graph_presentation() -> None:
    # Ohm's Law/metal-resistance-temperature-ден басқа тәжірибелер
    # scatter/fit/dedup-қа көшпеуі тиіс — Phase 38B: metal-resistance-
    # temperature ӘДЕЙІ Ohm's Law-мен БІРДЕЙ scatter+fit+manual-capture
    # механизмін қайта пайдаланады (X=температура, Y=кедергі).
    for experiment in ELECTRICITY_EXPERIMENTS:
        if experiment in (OHMS_LAW_EXPERIMENT, METAL_RESISTANCE_TEMPERATURE_EXPERIMENT):
            continue
        assert experiment.graph_connect_points is True
        assert experiment.graph_show_fit is False
        assert experiment.graph_title is None
        assert experiment.graph_dedup_x_tolerance == 0.0
        assert experiment.graph_dedup_y_tolerance == 0.0
        assert experiment.graph_capture_mode == "automatic"


def test_only_current_voltage_uses_stacked_graph() -> None:
    for experiment in ELECTRICITY_EXPERIMENTS:
        if experiment is CURRENT_VOLTAGE_EXPERIMENT:
            continue
        assert experiment.graph_stacked is False
        assert experiment.optional_display_channels == ()


# ---- Ohm's Law: manual point capture конфигурациясы (V2) ------------------


def test_ohms_law_uses_manual_point_capture() -> None:
    assert OHMS_LAW_EXPERIMENT.graph_capture_mode == "manual"
    assert OHMS_LAW_EXPERIMENT.graph_capture_sample_count == 10
    assert OHMS_LAW_EXPERIMENT.graph_capture_x_tolerance == 0.002
    assert OHMS_LAW_EXPERIMENT.graph_capture_y_tolerance == 0.02


def test_ohms_law_fit_equation_symbols() -> None:
    assert OHMS_LAW_EXPERIMENT.graph_fit_x_symbol == "I"
    assert OHMS_LAW_EXPERIMENT.graph_fit_y_symbol == "U"


# ---- Электр тізбегін құрастыру және ток күшін өлшеу: dual stacked
# time-series + optional Power (V3) ------------------------------------


def test_current_voltage_requires_voltage_and_current_sensors() -> None:
    assert CURRENT_VOLTAGE_EXPERIMENT.required_sensor_types == ("VOLTAGE", "CURRENT")
    assert CURRENT_VOLTAGE_EXPERIMENT.requires_multiple_sensors() is True


def test_current_voltage_is_time_series_not_ohms_law() -> None:
    # Бұл Ohm's Law ЕМЕС: X-Y тәуелділік/resistance/fit/scatter/manual
    # capture жоқ — уақыттық режим.
    assert CURRENT_VOLTAGE_EXPERIMENT.graph_x_channel is None
    assert CURRENT_VOLTAGE_EXPERIMENT.graph_mode == "time"
    assert CURRENT_VOLTAGE_EXPERIMENT.graph_show_fit is False
    assert CURRENT_VOLTAGE_EXPERIMENT.graph_capture_mode == "automatic"
    assert CURRENT_VOLTAGE_EXPERIMENT.graph_connect_points is True


def test_current_voltage_uses_stacked_dual_plot() -> None:
    assert CURRENT_VOLTAGE_EXPERIMENT.graph_stacked is True
    assert CURRENT_VOLTAGE_EXPERIMENT.graph_y_channels == ("voltage", "current")
    assert CURRENT_VOLTAGE_EXPERIMENT.graph_x_label == "Уақыт, t"
    assert CURRENT_VOLTAGE_EXPERIMENT.graph_stacked_titles == {
        "voltage": "Кернеудің уақыт бойынша өзгерісі",
        "current": "Ток күшінің уақыт бойынша өзгерісі",
    }
    assert CURRENT_VOLTAGE_EXPERIMENT.graph_stacked_y_labels == {
        "voltage": "Кернеу, U",
        "current": "Ток күші, I",
    }


def test_current_voltage_default_readouts_are_voltage_and_current_only() -> None:
    keys = [c.key for c in CURRENT_VOLTAGE_EXPERIMENT.get_display_channels()]
    assert keys == ["voltage", "current"]
    assert "resistance" not in keys
    assert "power" not in keys


def test_current_voltage_power_is_optional() -> None:
    optional_keys = [c.key for c in CURRENT_VOLTAGE_EXPERIMENT.get_optional_display_channels()]
    assert optional_keys == ["power"]
    assert CURRENT_VOLTAGE_EXPERIMENT.optional_display_show_label == "Қуатты көрсету"
    assert CURRENT_VOLTAGE_EXPERIMENT.optional_display_hide_label == "Қуатты жасыру"


def test_current_voltage_power_still_computed_via_formulas() -> None:
    # Power UI-де жасырын болса да, CalculationEngine оны есептей алады —
    # visibility != calculation.
    assert CURRENT_VOLTAGE_EXPERIMENT.formulas == {"power": "P = U × I"}
    derived_keys = {c.key for c in CURRENT_VOLTAGE_EXPERIMENT.derived_channels}
    assert "power" in derived_keys


def test_current_voltage_configuration_is_valid() -> None:
    assert CURRENT_VOLTAGE_EXPERIMENT.validate_configuration() == []


# ---- Phase 34: A/B delta measurement + physics-aware fit display name ----


def test_ohms_law_allows_delta_measurement() -> None:
    assert OHMS_LAW_EXPERIMENT.graph_allow_delta_measurement is True
    assert OHMS_LAW_EXPERIMENT.validate_configuration() == []


def test_ohms_law_has_physics_aware_fit_display_name() -> None:
    assert OHMS_LAW_EXPERIMENT.graph_fit_display_name == "Кедергі"


def test_current_voltage_allows_delta_measurement() -> None:
    assert CURRENT_VOLTAGE_EXPERIMENT.graph_allow_delta_measurement is True
    assert CURRENT_VOLTAGE_EXPERIMENT.validate_configuration() == []


def test_current_voltage_rate_of_change_left_unset() -> None:
    # §13 тек A/B cursor талап етті — dU/dt/dI/dt механизм генерик,
    # бірақ бұл тәжірибеде әдейі қосылмаған (locked-in scope decision).
    assert CURRENT_VOLTAGE_EXPERIMENT.graph_rate_of_change == ()


def test_other_experiments_do_not_allow_delta_measurement() -> None:
    _allowed = (
        OHMS_LAW_EXPERIMENT,
        CURRENT_VOLTAGE_EXPERIMENT,
        METAL_RESISTANCE_TEMPERATURE_EXPERIMENT,
    )
    for experiment in ELECTRICITY_EXPERIMENTS:
        if experiment in _allowed:
            continue
        assert experiment.graph_allow_delta_measurement is False


# ---- Phase 35: Experiment Guide wiring ------------------------------------


def test_ohms_law_has_guide_with_all_seven_sections() -> None:
    guide = OHMS_LAW_EXPERIMENT.guide
    assert guide is not None
    assert guide.objective
    assert guide.equipment
    assert guide.theory
    assert guide.formulas
    assert guide.procedure
    assert guide.safety
    assert guide.control_questions
    assert guide.validate() == []


def test_current_voltage_has_guide() -> None:
    guide = CURRENT_VOLTAGE_EXPERIMENT.guide
    assert guide is not None
    assert guide.objective
    assert guide.formulas
    assert guide.procedure
    assert guide.validate() == []


def test_current_work_power_has_guide() -> None:
    guide = CURRENT_WORK_POWER_EXPERIMENT.guide
    assert guide is not None
    assert guide.formulas == ("P = U × I", "A = ∫ P dt", "тұрақты P үшін A = P × t")
    assert guide.procedure
    assert guide.validate() == []


def test_ohms_law_guide_formulas_match_spec() -> None:
    assert OHMS_LAW_EXPERIMENT.guide.formulas == ("U = I × R", "R = U / I", "R = ΔU / ΔI")


def test_all_electricity_experiments_now_have_guide_and_report() -> None:
    # Phase 38B: series/parallel/metal-resistance-temperature ЕНДІ guide/
    # report алды — барлық 6 электр тәжірибесі (#3-8) №4-мен (Ohm's Law)
    # бірдей толықтық деңгейіне жетті.
    for experiment in ELECTRICITY_EXPERIMENTS:
        assert experiment.guide is not None
        assert experiment.report is not None


def test_all_implemented_experiments_still_validate_with_guide_present() -> None:
    for experiment in ELECTRICITY_EXPERIMENTS:
        if experiment.is_implemented:
            assert experiment.validate_configuration() == []


# ---- Phase 36.1: Wiring diagram wiring ------------------------------------


def test_ohms_law_has_wiring_diagram() -> None:
    diagram = OHMS_LAW_EXPERIMENT.diagram
    assert diagram is not None
    assert diagram.image_path.endswith("ohms_law_wiring.png")
    assert os.path.exists(diagram.image_path)
    assert diagram.caption
    assert diagram.validate() == []


def test_current_voltage_has_wiring_diagram() -> None:
    diagram = CURRENT_VOLTAGE_EXPERIMENT.diagram
    assert diagram is not None
    assert diagram.image_path.endswith("current_voltage_wiring.png")
    assert os.path.exists(diagram.image_path)
    assert diagram.validate() == []


def test_current_work_power_has_wiring_diagram() -> None:
    diagram = CURRENT_WORK_POWER_EXPERIMENT.diagram
    assert diagram is not None
    assert diagram.image_path.endswith("current_voltage_wiring.png")
    assert os.path.exists(diagram.image_path)
    assert diagram.validate() == []


def test_current_voltage_and_current_work_power_share_the_identical_diagram_image() -> None:
    """Электр тізбегін құрастыру және ток күшін өлшеу / Электр тогының
    жұмысы мен қуатын анықтау — дәл сол физикалық құрылым (2 сенсор +
    1 резистор breadboard-та), сондықтан дәл сол сурет файлын
    пайдалануы тиіс.
    """
    paths = {
        CURRENT_VOLTAGE_EXPERIMENT.diagram.image_path,
        CURRENT_WORK_POWER_EXPERIMENT.diagram.image_path,
    }
    assert len(paths) == 1


def test_ohms_law_has_its_own_diagram_file_distinct_from_current_voltage() -> None:
    """Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу ӨЗ
    файлын пайдаланады (``ohms_law_wiring.png``) — мазмұны Электр
    тізбегін құрастыру және ток күшін өлшеу суретімен әдейі БІРДЕЙ
    тізбекті бейнелейді, бірақ файл ретінде БӨЛЕК сақталған (пайдаланушы
    екеуін бөлек дайындады).
    """
    assert OHMS_LAW_EXPERIMENT.diagram.image_path != CURRENT_VOLTAGE_EXPERIMENT.diagram.image_path
    assert OHMS_LAW_EXPERIMENT.diagram.image_path.endswith("ohms_law_wiring.png")


def test_series_and_parallel_have_their_own_distinct_wiring_diagrams() -> None:
    """Series/Parallel — сол сенсорлар, БАСҚА тізбек топологиясы
    (бірнеше резистор), сондықтан ӨЗ, бір-бірінен және бір-резисторлы
    тәжірибелерден БӨЛЕК диаграмма файлдарын пайдаланады.
    """
    series_diagram = SERIES_CONNECTION_EXPERIMENT.diagram
    parallel_diagram = PARALLEL_CONNECTION_EXPERIMENT.diagram

    assert series_diagram is not None
    assert parallel_diagram is not None
    assert series_diagram.image_path.endswith("series_connection_wiring.png")
    assert parallel_diagram.image_path.endswith("parallel_connection_wiring.png")
    assert os.path.exists(series_diagram.image_path)
    assert os.path.exists(parallel_diagram.image_path)

    all_paths = {
        CURRENT_VOLTAGE_EXPERIMENT.diagram.image_path,
        OHMS_LAW_EXPERIMENT.diagram.image_path,
        CURRENT_WORK_POWER_EXPERIMENT.diagram.image_path,
        series_diagram.image_path,
        parallel_diagram.image_path,
    }
    assert all_paths == {
        CURRENT_VOLTAGE_EXPERIMENT.diagram.image_path,
        OHMS_LAW_EXPERIMENT.diagram.image_path,
        series_diagram.image_path,
        parallel_diagram.image_path,
    }  # тек 4 нақты БӨЛЕК файл (current-voltage/current-work-power ортақ)


def test_all_implemented_experiments_still_validate_with_diagram_present() -> None:
    for experiment in ELECTRICITY_EXPERIMENTS:
        if experiment.is_implemented:
            assert experiment.validate_configuration() == []


# =====================================================================
# Phase 38B: series/parallel guide+report, metal-resistance-temperature
# =====================================================================


def test_series_connection_has_guide_and_report() -> None:
    guide = SERIES_CONNECTION_EXPERIMENT.guide
    assert guide is not None
    assert guide.objective
    assert guide.theory
    assert guide.formulas
    assert guide.procedure
    assert guide.control_questions
    assert guide.validate() == []
    assert SERIES_CONNECTION_EXPERIMENT.report is not None


def test_parallel_connection_has_guide_and_report() -> None:
    guide = PARALLEL_CONNECTION_EXPERIMENT.guide
    assert guide is not None
    assert guide.objective
    assert guide.theory
    assert guide.formulas
    assert guide.procedure
    assert guide.control_questions
    assert guide.validate() == []
    assert PARALLEL_CONNECTION_EXPERIMENT.report is not None


def test_series_and_parallel_guides_have_distinct_theory() -> None:
    # Тізбектей/параллель теориясы бір-бірімен АУЫСТЫРЫЛМАУЫ тиіс —
    # R_жалпы=ΣRi (тізбектей) vs 1/R_жалпы=Σ(1/Ri) (параллель).
    series_theory = " ".join(SERIES_CONNECTION_EXPERIMENT.guide.theory)
    parallel_theory = " ".join(PARALLEL_CONNECTION_EXPERIMENT.guide.theory)
    assert series_theory != parallel_theory
    assert "R_жалпы = R₁ + R₂" in " ".join(SERIES_CONNECTION_EXPERIMENT.guide.formulas)
    assert "1 / R_жалпы" in " ".join(PARALLEL_CONNECTION_EXPERIMENT.guide.formulas)


def test_temperature_channel_definition() -> None:
    assert TEMPERATURE_CHANNEL.key == "temperature"
    assert TEMPERATURE_CHANNEL.unit == "°C"
    assert TEMPERATURE_CHANNEL.required is True


def test_metal_resistance_temperature_is_planned_until_firmware_exists() -> None:
    assert METAL_RESISTANCE_TEMPERATURE_EXPERIMENT.is_implemented is False


def test_metal_resistance_temperature_channels_and_formulas() -> None:
    experiment = METAL_RESISTANCE_TEMPERATURE_EXPERIMENT
    required_keys = {c.key for c in experiment.required_channels}
    derived_keys = {c.key for c in experiment.derived_channels}
    assert required_keys == {"temperature", "voltage", "current"}
    assert derived_keys == {"resistance"}
    assert experiment.formulas == {"resistance": "R = U / I"}


def test_metal_resistance_temperature_display_channel_order() -> None:
    keys = [c.key for c in METAL_RESISTANCE_TEMPERATURE_EXPERIMENT.get_display_channels()]
    assert keys == ["temperature", "voltage", "current", "resistance"]


def test_metal_resistance_temperature_uses_scatter_fit_manual_capture_like_ohms_law() -> None:
    experiment = METAL_RESISTANCE_TEMPERATURE_EXPERIMENT
    assert experiment.graph_x_channel == "temperature"
    assert experiment.graph_y_channels == ("resistance",)
    assert experiment.graph_mode == "xy"
    assert experiment.graph_connect_points is False
    assert experiment.graph_show_fit is True
    assert experiment.graph_capture_mode == "manual"
    assert experiment.graph_fit_x_symbol == "T"
    assert experiment.graph_fit_y_symbol == "R"
    assert experiment.graph_fit_result_prefix == "k"
    assert experiment.graph_fit_unit == "Ω/°C"


def test_metal_resistance_temperature_has_guide_report_and_diagram() -> None:
    experiment = METAL_RESISTANCE_TEMPERATURE_EXPERIMENT
    guide = experiment.guide
    assert guide is not None
    assert guide.objective
    assert guide.theory
    assert guide.procedure
    assert guide.validate() == []
    assert experiment.report is not None
    assert experiment.diagram is not None
    assert os.path.exists(experiment.diagram.image_path)
    assert experiment.diagram.validate() == []


def test_metal_resistance_temperature_equipment_notes_planned_sensor() -> None:
    # Пайдаланушының нақты талабы: температура сенсоры "жоспарланған, әлі
    # қосылмаған" деп ашық белгіленуі тиіс — жалған дайын hardware ЖОҚ.
    equipment_text = " ".join(METAL_RESISTANCE_TEMPERATURE_EXPERIMENT.guide.equipment)
    assert "жоспарланған" in equipment_text
    assert "қосылмаған" in equipment_text


# =====================================================================
# Phase 39A: үш деңгейлі кері байланыс/бағалау конфигурациясы
# =====================================================================


def test_all_six_electricity_experiments_have_assessment_configured() -> None:
    for experiment in ELECTRICITY_EXPERIMENTS:
        assert experiment.assessment is not None, experiment.id


def test_all_assessments_have_exactly_five_level1_questions() -> None:
    for experiment in ELECTRICITY_EXPERIMENTS:
        assert len(experiment.assessment.level1_questions) == 5, experiment.id


def test_all_assessments_have_level2_and_level3_questions() -> None:
    for experiment in ELECTRICITY_EXPERIMENTS:
        assessment = experiment.assessment
        assert 3 <= len(assessment.level2_questions) <= 4, experiment.id
        assert len(assessment.level3_questions) == 3, experiment.id


def test_all_assessments_validate_with_no_errors() -> None:
    for experiment in ELECTRICITY_EXPERIMENTS:
        assert experiment.assessment.validate() == [], experiment.id


def test_all_assessments_have_unique_question_ids_within_experiment() -> None:
    for experiment in ELECTRICITY_EXPERIMENTS:
        assessment = experiment.assessment
        all_ids = [
            q.id
            for q in (
                *assessment.level1_questions,
                *assessment.level2_questions,
                *assessment.level3_questions,
            )
        ]
        assert len(all_ids) == len(set(all_ids)), experiment.id


def test_all_multiple_choice_questions_have_exactly_one_correct_answer_in_range() -> None:
    for experiment in ELECTRICITY_EXPERIMENTS:
        for question in experiment.assessment.level1_questions:
            assert 0 <= question.correct_option_index < len(question.options)
            assert len(question.options) >= 2


def test_all_assessments_use_default_one_to_five_self_assessment_scale() -> None:
    for experiment in ELECTRICITY_EXPERIMENTS:
        assessment = experiment.assessment
        assert assessment.self_assessment_min == 1
        assert assessment.self_assessment_max == 5


def test_metal_resistance_temperature_assessment_frames_hardware_limitation_neutrally() -> None:
    # §8: "hardware limitation must not be presented as student failure".
    assessment = METAL_RESISTANCE_TEMPERATURE_EXPERIMENT.assessment
    all_text_parts = [
        q.prompt for q in (*assessment.level1_questions, *assessment.level2_questions)
    ]
    for question in assessment.level1_questions:
        all_text_parts.extend(question.options)
    all_text = " ".join(all_text_parts)
    assert "қатесі емес" in all_text


def test_question_content_lives_in_config_not_hardcoded_in_dialog_widget() -> None:
    """§ "Questions must not be hardcoded inside the widget": диалог
    файлында ешбір нақты сұрақ мәтіні (тек generic placeholder/UI
    мәтіндер) болмауы тиіс — барлық НАҚТЫ сұрақ мазмұны
    ``experiments_config.py``-де ғана өмір сүреді.
    """
    import inspect

    from ui.widgets import experiment_feedback_dialog

    source = inspect.getsource(experiment_feedback_dialog)
    # Кез келген electricity тәжірибесінің нақты сұрақ мәтіні дедлог
    # кодында СӨЗБЕ-СӨЗ кездеспеуі тиіс.
    for experiment in ELECTRICITY_EXPERIMENTS:
        for question in experiment.assessment.level1_questions:
            assert question.prompt not in source
