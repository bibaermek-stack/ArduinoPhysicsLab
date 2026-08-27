"""ExperimentDefinition үшін юнит-тесттер: конфигурация валидациясы."""

import pytest

from domain.entities.experiment_definition import (
    ExperimentDefinition,
    ExperimentDiagram,
    ExperimentGuide,
    ExperimentReport,
    RateOfChangeConfig,
)
from domain.entities.sensor_channel import SensorChannel


def _voltage_channel() -> SensorChannel:
    return SensorChannel(
        key="voltage", display_name="Кернеу", unit="V", minimum=0.0, maximum=10.0
    )


def _current_channel() -> SensorChannel:
    return SensorChannel(
        key="current", display_name="Ток күші", unit="A", minimum=0.0, maximum=2.0
    )


def _resistance_channel() -> SensorChannel:
    return SensorChannel(
        key="resistance",
        display_name="Кедергі",
        unit="Ω",
        minimum=0.0,
        maximum=None,
        required=False,
    )


def test_valid_configuration_returns_no_errors() -> None:
    definition = ExperimentDefinition(
        id="e02",
        title="Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу",
        description="Кернеу мен ток күшінен кедергіні есептеу",
        required_channels=(_voltage_channel(), _current_channel()),
        derived_channels=(_resistance_channel(),),
        graph_x_channel="voltage",
        graph_y_channels=("current",),
        formulas={"resistance": "voltage / current"},
    )
    assert definition.validate_configuration() == []


def test_empty_required_channels_returns_error() -> None:
    definition = ExperimentDefinition(id="e00", title="Бос тәжірибе", description="")
    errors = definition.validate_configuration()
    assert any("required_channels" in error for error in errors)


def test_duplicate_channel_key_is_detected() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Қайталанған арна",
        description="",
        required_channels=(_voltage_channel(),),
        derived_channels=(_voltage_channel(),),
    )
    errors = definition.validate_configuration()
    assert any("voltage" in error for error in errors)


def test_unknown_graph_x_channel_returns_error() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Белгісіз X арна",
        description="",
        required_channels=(_voltage_channel(),),
        graph_x_channel="unknown_channel",
    )
    errors = definition.validate_configuration()
    assert any("unknown_channel" in error for error in errors)


def test_unknown_graph_y_channel_returns_error() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Белгісіз Y арна",
        description="",
        required_channels=(_voltage_channel(),),
        graph_y_channels=("unknown_channel",),
    )
    errors = definition.validate_configuration()
    assert any("unknown_channel" in error for error in errors)


def test_formula_referencing_unknown_derived_channel_returns_error() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Белгісіз формула кілті",
        description="",
        required_channels=(_voltage_channel(), _current_channel()),
        derived_channels=(_resistance_channel(),),
        formulas={"power": "voltage * current"},
    )
    errors = definition.validate_configuration()
    assert any("power" in error for error in errors)


def test_empty_id_raises_value_error() -> None:
    with pytest.raises(ValueError):
        ExperimentDefinition(id="", title="Атауы бар", description="")


def test_empty_title_raises_value_error() -> None:
    with pytest.raises(ValueError):
        ExperimentDefinition(id="e01", title="", description="")


def test_unknown_display_channel_returns_error() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Белгісіз display арна",
        description="",
        required_channels=(_voltage_channel(),),
        display_channels=("unknown_channel",),
    )
    errors = definition.validate_configuration()
    assert any("unknown_channel" in error for error in errors)


# ---- get_display_channels() ----------------------------------------------


def test_get_display_channels_defaults_to_required_then_derived() -> None:
    voltage = _voltage_channel()
    current = _current_channel()
    resistance = _resistance_channel()
    definition = ExperimentDefinition(
        id="e02",
        title="Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу",
        description="",
        required_channels=(voltage, current),
        derived_channels=(resistance,),
    )

    assert definition.get_display_channels() == (voltage, current, resistance)


def test_get_display_channels_uses_explicit_order() -> None:
    voltage = _voltage_channel()
    current = _current_channel()
    resistance = _resistance_channel()
    definition = ExperimentDefinition(
        id="e02",
        title="Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу",
        description="",
        required_channels=(voltage, current),
        derived_channels=(resistance,),
        display_channels=("resistance", "voltage"),
    )

    assert definition.get_display_channels() == (resistance, voltage)


# ---- required_sensor_types / requires_multiple_sensors() -----------------


def test_default_required_sensor_types_is_empty() -> None:
    definition = ExperimentDefinition(id="e01", title="Тест", description="")

    assert definition.required_sensor_types == ()
    assert definition.requires_multiple_sensors() is False


def test_single_required_sensor_type_does_not_require_multiple() -> None:
    definition = ExperimentDefinition(
        id="e01", title="Тест", description="", required_sensor_types=("VOLTAGE",)
    )

    assert definition.requires_multiple_sensors() is False


def test_two_required_sensor_types_requires_multiple() -> None:
    definition = ExperimentDefinition(
        id="ohms-law",
        title="Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу",
        description="",
        required_channels=(_voltage_channel(), _current_channel()),
        required_sensor_types=("VOLTAGE", "CURRENT"),
    )

    assert definition.requires_multiple_sensors() is True


def test_duplicate_required_sensor_type_returns_error() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(),),
        required_sensor_types=("VOLTAGE", "VOLTAGE"),
    )

    errors = definition.validate_configuration()

    assert any("VOLTAGE" in error for error in errors)


# ---- Graph presentation конфигурациясы (scatter+fit, V1) -----------------


def test_graph_presentation_defaults_preserve_old_behavior() -> None:
    definition = ExperimentDefinition(id="e01", title="Тест", description="")

    assert definition.graph_connect_points is True
    assert definition.graph_show_fit is False
    assert definition.graph_title is None
    assert definition.graph_x_label is None
    assert definition.graph_y_label is None
    assert definition.graph_dedup_x_tolerance == 0.0
    assert definition.graph_dedup_y_tolerance == 0.0
    assert definition.graph_fit_result_prefix == "slope"
    assert definition.graph_fit_unit is None


def test_graph_mode_is_time_when_no_x_channel() -> None:
    definition = ExperimentDefinition(
        id="e01", title="Тест", description="", required_channels=(_voltage_channel(),)
    )

    assert definition.graph_mode == "time"


def test_graph_mode_is_xy_when_x_channel_given() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(), _current_channel()),
        graph_x_channel="voltage",
        graph_y_channels=("current",),
    )

    assert definition.graph_mode == "xy"


def test_negative_dedup_x_tolerance_returns_error() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(),),
        graph_dedup_x_tolerance=-0.1,
    )

    errors = definition.validate_configuration()

    assert any("graph_dedup_x_tolerance" in error for error in errors)


def test_negative_dedup_y_tolerance_returns_error() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(),),
        graph_dedup_y_tolerance=-0.1,
    )

    errors = definition.validate_configuration()

    assert any("graph_dedup_y_tolerance" in error for error in errors)


def test_show_fit_without_x_channel_returns_error() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(),),
        graph_show_fit=True,
    )

    errors = definition.validate_configuration()

    assert any("graph_show_fit" in error for error in errors)


def test_show_fit_with_x_channel_is_valid() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(), _current_channel()),
        graph_x_channel="current",
        graph_y_channels=("voltage",),
        graph_show_fit=True,
    )

    assert definition.validate_configuration() == []


# ---- Manual point capture конфигурациясы (V2) -----------------------------


def test_capture_defaults_preserve_automatic_behavior() -> None:
    definition = ExperimentDefinition(id="e01", title="Тест", description="")

    assert definition.graph_capture_mode == "automatic"
    assert definition.graph_capture_sample_count == 10
    assert definition.graph_capture_x_tolerance == 0.002
    assert definition.graph_capture_y_tolerance == 0.02
    assert definition.graph_fit_x_symbol == "X"
    assert definition.graph_fit_y_symbol == "Y"


def test_invalid_capture_mode_value_returns_error() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(), _current_channel()),
        graph_x_channel="current",
        graph_capture_mode="bogus",
    )

    errors = definition.validate_configuration()

    assert any("graph_capture_mode" in error for error in errors)


def test_zero_capture_sample_count_returns_error() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(),),
        graph_capture_sample_count=0,
    )

    errors = definition.validate_configuration()

    assert any("graph_capture_sample_count" in error for error in errors)


def test_negative_capture_tolerances_return_errors() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(),),
        graph_capture_x_tolerance=-0.1,
        graph_capture_y_tolerance=-0.1,
    )

    errors = definition.validate_configuration()

    assert any("graph_capture_x_tolerance" in error for error in errors)
    assert any("graph_capture_y_tolerance" in error for error in errors)


def test_manual_capture_mode_without_x_channel_returns_error() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(),),
        graph_capture_mode="manual",
    )

    errors = definition.validate_configuration()

    assert any("graph_capture_mode" in error for error in errors)


def test_manual_capture_mode_with_x_channel_is_valid() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(), _current_channel()),
        graph_x_channel="current",
        graph_y_channels=("voltage",),
        graph_capture_mode="manual",
        graph_show_fit=True,
    )

    assert definition.validate_configuration() == []


# ---- Stacked time-series graph / optional display channels (V3) ----------


def test_stacked_and_optional_defaults() -> None:
    definition = ExperimentDefinition(id="e01", title="Тест", description="")

    assert definition.graph_stacked is False
    assert definition.graph_stacked_titles == {}
    assert definition.graph_stacked_y_labels == {}
    assert definition.optional_display_channels == ()
    assert definition.optional_display_show_label == "Қосымша мәндерді көрсету"
    assert definition.optional_display_hide_label == "Қосымша мәндерді жасыру"
    assert definition.diagram is None


def test_stacked_with_x_channel_returns_error() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(), _current_channel()),
        graph_x_channel="current",
        graph_y_channels=("voltage",),
        graph_stacked=True,
    )

    errors = definition.validate_configuration()

    assert any("graph_stacked" in error for error in errors)


def test_stacked_with_fit_returns_error() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(), _current_channel()),
        graph_y_channels=("voltage", "current"),
        graph_stacked=True,
        graph_show_fit=True,
    )

    errors = definition.validate_configuration()

    assert any("graph_stacked" in error for error in errors)


def test_stacked_time_series_is_valid() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(), _current_channel()),
        graph_x_channel=None,
        graph_y_channels=("voltage", "current"),
        graph_stacked=True,
        graph_stacked_titles={"voltage": "U(t)", "current": "I(t)"},
    )

    assert definition.validate_configuration() == []


def test_unknown_optional_display_channel_returns_error() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(),),
        optional_display_channels=("bogus_key",),
    )

    errors = definition.validate_configuration()

    assert any("optional_display_channels" in error for error in errors)


def test_optional_display_channel_overlapping_display_channels_returns_error() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(), _current_channel()),
        display_channels=("voltage", "current"),
        optional_display_channels=("current",),
    )

    errors = definition.validate_configuration()

    assert any("display_channels" in error for error in errors)


def test_get_optional_display_channels_resolves_known_key() -> None:
    voltage = _voltage_channel()
    current = _current_channel()
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(voltage, current),
        display_channels=("voltage",),
        optional_display_channels=("current",),
    )

    assert definition.get_optional_display_channels() == (current,)


def test_get_optional_display_channels_unknown_key_falls_back_to_key_as_label() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(),),
        optional_display_channels=("bogus_key",),
    )

    channels = definition.get_optional_display_channels()

    assert channels[0].key == "bogus_key"
    assert channels[0].display_name == "bogus_key"


def test_get_display_channels_unknown_key_falls_back_to_key_as_label() -> None:
    voltage = _voltage_channel()
    definition = ExperimentDefinition(
        id="e02",
        title="Тест",
        description="",
        required_channels=(voltage,),
        display_channels=("voltage", "bogus_key"),
    )

    channels = definition.get_display_channels()

    assert channels[0] is voltage
    assert channels[1].key == "bogus_key"
    assert channels[1].display_name == "bogus_key"
    assert channels[1].unit == ""


# ---- Phase 34: delta measurement / rate-of-change / fit display name ----


def test_phase34_defaults_preserve_old_behavior() -> None:
    definition = ExperimentDefinition(id="e01", title="Тест", description="")

    assert definition.graph_allow_delta_measurement is False
    assert definition.graph_rate_of_change == ()
    assert definition.graph_fit_display_name is None


def test_rate_of_change_unknown_channel_key_returns_error() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(), _current_channel()),
        graph_x_channel=None,
        graph_y_channels=("voltage", "current"),
        graph_rate_of_change=(
            RateOfChangeConfig(channel_key="bogus", symbol="dX/dt", display_name="X", unit="X/s"),
        ),
    )

    errors = definition.validate_configuration()

    assert any("graph_rate_of_change" in error for error in errors)


def test_rate_of_change_channel_not_in_graph_y_channels_returns_error() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(), _current_channel()),
        graph_x_channel=None,
        graph_y_channels=("voltage",),
        graph_rate_of_change=(
            RateOfChangeConfig(
                channel_key="current", symbol="dI/dt", display_name="Ток жылдамдығы", unit="A/s"
            ),
        ),
    )

    errors = definition.validate_configuration()

    assert any("graph_rate_of_change" in error for error in errors)


def test_rate_of_change_rejected_in_xy_mode() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(), _current_channel()),
        graph_x_channel="current",
        graph_y_channels=("voltage",),
        graph_rate_of_change=(
            RateOfChangeConfig(
                channel_key="voltage", symbol="dU/dt", display_name="Кернеу жылдамдығы", unit="V/s"
            ),
        ),
    )

    errors = definition.validate_configuration()

    assert any("graph_rate_of_change" in error for error in errors)


def test_rate_of_change_duplicate_channel_key_returns_error() -> None:
    config = RateOfChangeConfig(
        channel_key="voltage", symbol="dU/dt", display_name="Кернеу жылдамдығы", unit="V/s"
    )
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(), _current_channel()),
        graph_x_channel=None,
        graph_y_channels=("voltage", "current"),
        graph_rate_of_change=(config, config),
    )

    errors = definition.validate_configuration()

    assert any("бірнеше рет" in error for error in errors)


def test_rate_of_change_valid_time_series_configuration() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(), _current_channel()),
        graph_x_channel=None,
        graph_y_channels=("voltage", "current"),
        graph_rate_of_change=(
            RateOfChangeConfig(
                channel_key="voltage", symbol="dU/dt", display_name="Кернеу жылдамдығы", unit="V/s"
            ),
        ),
    )

    assert definition.validate_configuration() == []


def test_allow_delta_measurement_is_valid_bool_flag() -> None:
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(),),
        graph_allow_delta_measurement=True,
    )

    assert definition.validate_configuration() == []
    assert definition.graph_allow_delta_measurement is True


# ---- Phase 35: ExperimentGuide model + validation ------------------------


def test_experiment_guide_defaults_are_all_empty() -> None:
    guide = ExperimentGuide()

    assert guide.objective == ()
    assert guide.equipment == ()
    assert guide.theory == ""
    assert guide.formulas == ()
    assert guide.procedure == ()
    assert guide.safety == ()
    assert guide.control_questions == ()
    assert guide.validate() == []


def test_experiment_guide_well_formed_content_is_valid() -> None:
    guide = ExperimentGuide(
        objective=("Мақсат 1", "Мақсат 2"),
        equipment=("Кернеу датчигі",),
        theory="Қысқа теория.",
        formulas=("U = I × R", "R = U / I"),
        procedure=("Қадам 1.", "Қадам 2."),
        safety=("Ережe 1.",),
        control_questions=("Сұрақ 1?",),
    )

    assert guide.validate() == []


def test_experiment_definition_default_guide_is_none_and_valid() -> None:
    """Backward compatibility: ескі (guide-сыз) ExperimentDefinition
    ӨЗГЕРІССІЗ жарамды қалады — жаңа өріс тек ЖАҢА тәжірибелерге
    қосымша, ешбір ескі шақыру бұзылмайды.
    """
    definition = ExperimentDefinition(
        id="e01", title="Тест", description="", required_channels=(_voltage_channel(),)
    )

    assert definition.guide is None
    assert definition.validate_configuration() == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"objective": ["Мақсат 1"]},  # list, tuple ЕМЕС
        {"equipment": ("Ok", 5)},  # tuple ішінде int
        {"formulas": "U = IR"},  # str, tuple ЕМЕС (жол өзі iterable болса да)
        {"procedure": (1, 2, 3)},  # int-тер tuple-і
        {"safety": ({"a": 1},)},  # dict элемент
        {"control_questions": [1, 2]},  # list of int
        {"theory": 12345},  # int, str ЕМЕС
    ],
)
def test_experiment_guide_malformed_fields_return_errors(kwargs) -> None:
    guide = ExperimentGuide(**kwargs)

    errors = guide.validate()

    assert errors != []


def test_experiment_definition_with_malformed_guide_surfaces_errors() -> None:
    guide = ExperimentGuide(procedure=(1, 2))  # malformed
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(),),
        guide=guide,
    )

    errors = definition.validate_configuration()

    assert any("ExperimentGuide" in error for error in errors)


def test_experiment_guide_optional_sections_can_be_empty() -> None:
    """§6: safety=() / control_questions=() толық жарамды — UI-де
    тиісті секция ЖАСЫРЫН болады, бірақ config деңгейінде қате ЕМЕС.
    """
    guide = ExperimentGuide(
        objective=("Мақсат",),
        formulas=("U = IR",),
        safety=(),
        control_questions=(),
    )

    assert guide.validate() == []


# ---- Phase 36: ExperimentReport model + validation -----------------------


def test_experiment_report_defaults() -> None:
    report = ExperimentReport()

    assert report.title == "Зертханалық есеп"
    assert report.conclusion_prompt == ""
    assert report.validate() == []


def test_experiment_report_custom_values_are_valid() -> None:
    report = ExperimentReport(title="Есеп", conclusion_prompt="Қорытынды жазыңыз.")

    assert report.validate() == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"title": 12345},
        {"conclusion_prompt": ["not", "a", "string"]},
    ],
)
def test_experiment_report_malformed_fields_return_errors(kwargs) -> None:
    report = ExperimentReport(**kwargs)

    assert report.validate() != []


def test_experiment_definition_default_report_is_none_and_valid() -> None:
    """Backward compatibility: ескі (report-сыз) ExperimentDefinition
    ӨЗГЕРІССІЗ жарамды қалады.
    """
    definition = ExperimentDefinition(
        id="e01", title="Тест", description="", required_channels=(_voltage_channel(),)
    )

    assert definition.report is None
    assert definition.validate_configuration() == []


def test_experiment_definition_with_malformed_report_surfaces_errors() -> None:
    report = ExperimentReport(title=999)
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(),),
        report=report,
    )

    errors = definition.validate_configuration()

    assert any("ExperimentReport" in error for error in errors)


# ---- Phase 36.1: ExperimentDiagram model + validation ---------------------


def test_experiment_diagram_defaults() -> None:
    diagram = ExperimentDiagram(image_path="ui/resources/images/current_voltage_wiring.png")

    assert diagram.caption == ""
    assert diagram.validate() == []


def test_experiment_diagram_custom_values_are_valid() -> None:
    diagram = ExperimentDiagram(
        image_path="ui/resources/images/current_voltage_wiring.png",
        caption="Қызыл сым — оң полюс, қара сым — теріс полюс.",
    )

    assert diagram.validate() == []


def test_experiment_diagram_empty_image_path_returns_error() -> None:
    diagram = ExperimentDiagram(image_path="")

    errors = diagram.validate()

    assert any("image_path" in error for error in errors)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"image_path": 12345},
        {"image_path": "path.png", "caption": ["not", "a", "string"]},
    ],
)
def test_experiment_diagram_malformed_fields_return_errors(kwargs) -> None:
    diagram = ExperimentDiagram(**kwargs)

    assert diagram.validate() != []


def test_experiment_definition_default_diagram_is_none_and_valid() -> None:
    """Backward compatibility: ескі (diagram-сыз) ExperimentDefinition
    ӨЗГЕРІССІЗ жарамды қалады.
    """
    definition = ExperimentDefinition(
        id="e01", title="Тест", description="", required_channels=(_voltage_channel(),)
    )

    assert definition.diagram is None
    assert definition.validate_configuration() == []


def test_experiment_definition_with_malformed_diagram_surfaces_errors() -> None:
    diagram = ExperimentDiagram(image_path="")
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(_voltage_channel(),),
        diagram=diagram,
    )

    errors = definition.validate_configuration()

    assert any("ExperimentDiagram" in error for error in errors)
