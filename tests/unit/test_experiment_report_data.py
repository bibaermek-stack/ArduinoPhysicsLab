"""domain.services.experiment_report_data (Phase 36) үшін юнит-тесттер —
таза функциялар, Qt қажет емес. Барлық статистика/fit/қуат/жұмыс
БҰРЫННАН БАР domain.services.graph_analysis функцияларын қайта
пайдаланады — бұл тесттер сол реюзды НАҚТЫ дерекпен растайды.
"""

from datetime import datetime, timedelta, timezone

import pytest

from domain.entities.experiment_definition import ExperimentDefinition
from domain.entities.experiment_session import ExperimentSession
from domain.entities.measurement import Measurement
from domain.entities.sensor_channel import SensorChannel
from domain.services.experiment_report_data import build_experiment_report_data
from domain.services.graph_analysis import DERIVED_ANALYSIS_POWER_ENERGY

VOLTAGE = SensorChannel(key="voltage", display_name="Кернеу", unit="V", decimals=3)
CURRENT = SensorChannel(key="current", display_name="Ток", unit="A", decimals=3)
POWER = SensorChannel(key="power", display_name="Қуат", unit="W", decimals=3, required=False)
RESISTANCE = SensorChannel(
    key="resistance", display_name="Кедергі", unit="Ω", decimals=2, required=False
)

_STARTED = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _make_session(experiment_id: str = "e01") -> ExperimentSession:
    return ExperimentSession(id="s1", experiment_id=experiment_id, started_at=_STARTED)


def _add(session: ExperimentSession, values: dict, derived: dict | None = None, offset_s: float = 0.0) -> None:
    session.add_measurement(
        Measurement(
            timestamp=_STARTED + timedelta(seconds=offset_s),
            values=values,
            experiment_id=session.experiment_id,
            derived_values=derived or {},
        )
    )


def _ohms_law_like_definition() -> ExperimentDefinition:
    return ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(VOLTAGE, CURRENT),
        derived_channels=(RESISTANCE,),
        graph_x_channel="current",
        graph_y_channels=("voltage",),
        graph_show_fit=True,
        graph_fit_result_prefix="R",
        graph_fit_unit="Ω",
        graph_fit_x_symbol="I",
        graph_fit_y_symbol="U",
        graph_fit_display_name="Кедергі",
    )


def _time_series_power_definition() -> ExperimentDefinition:
    return ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(VOLTAGE, CURRENT),
        derived_channels=(POWER,),
        graph_x_channel=None,
        graph_y_channels=("power",),
        graph_derived_analysis=DERIVED_ANALYSIS_POWER_ENERGY,
    )


# ---- channel_statistics ---------------------------------------------------


def test_channel_statistics_known_values() -> None:
    session = _make_session()
    for i, voltage in enumerate((1.0, 2.0, 3.0, 4.0)):
        _add(session, {"voltage": voltage, "current": 0.1}, offset_s=i)

    data = build_experiment_report_data(_ohms_law_like_definition(), session)

    voltage_stats = next(c for c in data.channel_statistics if c.channel_key == "voltage")
    assert voltage_stats.n == 4
    assert voltage_stats.latest == pytest.approx(4.0)  # соңғы мән
    assert voltage_stats.minimum == pytest.approx(1.0)
    assert voltage_stats.maximum == pytest.approx(4.0)
    assert voltage_stats.average == pytest.approx(2.5)


def test_channel_statistics_missing_channel_returns_none_fields_not_zero() -> None:
    """Resistance ешбір Measurement-те жоқ — n=0, барлық өріс None
    (жалған 0.0 ЕШҚАШАН қайтарылмайды).
    """
    session = _make_session()
    _add(session, {"voltage": 1.0, "current": 0.1})

    data = build_experiment_report_data(_ohms_law_like_definition(), session)

    resistance_stats = next(c for c in data.channel_statistics if c.channel_key == "resistance")
    assert resistance_stats.n == 0
    assert resistance_stats.latest is None
    assert resistance_stats.minimum is None
    assert resistance_stats.maximum is None
    assert resistance_stats.average is None


def test_empty_session_produces_zero_counts_no_crash() -> None:
    session = _make_session()

    data = build_experiment_report_data(_ohms_law_like_definition(), session)

    assert data.sample_count == 0
    for stats in data.channel_statistics:
        assert stats.n == 0
        assert stats.latest is None


# ---- fit_result -------------------------------------------------------


def test_fit_result_computed_for_show_fit_experiment() -> None:
    session = _make_session()
    resistance = 87.68
    for i, current in enumerate((0.02, 0.03, 0.04, 0.05)):
        _add(session, {"voltage": resistance * current, "current": current}, offset_s=i)

    data = build_experiment_report_data(_ohms_law_like_definition(), session)

    assert data.fit_result is not None
    assert data.fit_result.valid is True
    assert data.fit_result.slope == pytest.approx(resistance, rel=1e-6)
    assert data.fit_x_symbol == "I"
    assert data.fit_y_symbol == "U"
    assert data.fit_result_prefix == "R"
    assert data.fit_unit == "Ω"
    assert data.fit_display_name == "Кедергі"


def test_fit_result_none_when_experiment_does_not_show_fit() -> None:
    session = _make_session()
    for i in range(4):
        _add(session, {"voltage": 5.0 + i * 0.5, "current": 0.06 + i * 0.01}, offset_s=i)

    data = build_experiment_report_data(_time_series_power_definition(), session)

    assert data.fit_result is None


def test_fit_result_none_with_insufficient_points() -> None:
    session = _make_session()
    _add(session, {"voltage": 1.0, "current": 0.1})

    data = build_experiment_report_data(_ohms_law_like_definition(), session)

    assert data.fit_result is None


# ---- power_average / work_energy ---------------------------------------


def test_power_average_none_when_experiment_has_no_power_channel() -> None:
    session = _make_session()
    _add(session, {"voltage": 1.0, "current": 0.1})

    data = build_experiment_report_data(_ohms_law_like_definition(), session)

    assert data.power_average is None
    assert data.work_energy is None


def test_power_average_computed_when_power_channel_present() -> None:
    session = _make_session()
    for i in range(4):
        _add(
            session,
            {"voltage": 5.0, "current": 0.1},
            derived={"power": 0.5},
            offset_s=i,
        )

    data = build_experiment_report_data(_time_series_power_definition(), session)

    assert data.power_average == pytest.approx(0.5)


def test_work_energy_matches_trapezoidal_integral_of_constant_power() -> None:
    """P(t) = 2W тұрақты, t: 0..10s -> W = 2*10 = 20 J (дәл, §19-дағы
    domain тестімен БІРДЕЙ белгілі мысал).
    """
    session = _make_session()
    for offset_s in (0.0, 2.0, 4.0, 6.0, 8.0, 10.0):
        _add(session, {"voltage": 4.0, "current": 0.5}, derived={"power": 2.0}, offset_s=offset_s)

    data = build_experiment_report_data(_time_series_power_definition(), session)

    assert data.work_energy == pytest.approx(20.0)


def test_work_energy_none_for_xy_mode_experiment() -> None:
    """graph_x_channel берілген (XY режим) тәжірибеде work/energy
    есептелмейді — тек уақыттық режимде мағыналы.
    """
    definition = ExperimentDefinition(
        id="e01",
        title="Тест",
        description="",
        required_channels=(VOLTAGE, CURRENT),
        derived_channels=(POWER,),
        graph_x_channel="voltage",  # XY режим
        graph_y_channels=("current",),
    )
    session = _make_session()
    for i in range(4):
        _add(session, {"voltage": 5.0, "current": 0.1}, derived={"power": 0.5}, offset_s=i)

    data = build_experiment_report_data(definition, session)

    assert data.power_average == pytest.approx(0.5)  # арна бар, average есептеледі
    assert data.work_energy is None  # тек time-series-те integral мағыналы


# ---- duration/sample_count ---------------------------------------------


def test_sample_count_and_duration_from_session() -> None:
    session = _make_session()
    for i in range(5):
        _add(session, {"voltage": 1.0, "current": 0.1}, offset_s=i)
    session.stop()

    data = build_experiment_report_data(_ohms_law_like_definition(), session)

    assert data.sample_count == 5
    assert data.duration_seconds == pytest.approx(session.duration_seconds())


def test_single_sample_edge_case_does_not_crash() -> None:
    session = _make_session()
    _add(session, {"voltage": 3.3, "current": 0.15})

    data = build_experiment_report_data(_ohms_law_like_definition(), session)

    voltage_stats = next(c for c in data.channel_statistics if c.channel_key == "voltage")
    assert voltage_stats.n == 1
    assert voltage_stats.latest == pytest.approx(3.3)
    assert voltage_stats.minimum == voltage_stats.maximum == pytest.approx(3.3)
    assert data.fit_result is None  # 1 нүкте жеткіліксіз
