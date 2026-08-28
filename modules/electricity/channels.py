"""Тұрақты электр тогы тәжірибелерінің ортақ SensorChannel анықтамалары.

Arduino протоколы (``docs/serial_protocol.md``) voltage/current жібереді;
туынды арналарды ``CalculationEngine`` есептейді. Каталог
``experiments_config`` осы константаларды қайта экспорттайды — импорт
жолдары өзгермейді.
"""

from domain.entities.sensor_channel import SensorChannel

VOLTAGE_CHANNEL = SensorChannel(
    key="voltage", display_name="Кернеу", unit="V", minimum=0.0, maximum=30.0, decimals=3
)
CURRENT_CHANNEL = SensorChannel(
    key="current", display_name="Ток", unit="A", minimum=0.0, maximum=5.0, decimals=3
)
RESISTANCE_CHANNEL = SensorChannel(
    key="resistance",
    display_name="Кедергі",
    unit="Ω",
    minimum=0.0,
    decimals=2,
    required=False,
)
POWER_CHANNEL = SensorChannel(
    key="power", display_name="Қуат", unit="W", minimum=0.0, decimals=3, required=False
)
WORK_CHANNEL = SensorChannel(
    key="work", display_name="Жұмыс", unit="J", minimum=0.0, decimals=3, required=False
)
# Пакеттегі "T=" өрісінен келеді (PacketParser._KEY_MAP: "T" -> "time").
# required=False: T= жіберілмесе де DataValidator қатесі шықпайды — graph/table
# өз ішінде elapsed-time fallback қолданады, тек current-work-power жұмысында
# нақты уақыт readout ретінде көрсету үшін ғана required_channels-те тұр.
TIME_CHANNEL = SensorChannel(
    key="time", display_name="Уақыт", unit="s", minimum=0.0, decimals=2, required=False
)
# Phase 38B: "Металдар кедергісінің температураға тәуелділігі" (№8)
# тәжірибесінің X арнасы. Нақты температура сенсоры firmware-і әлі жоқ
# (domain/constants/sensor_types.py-дегі ENERGY/OHMMETER-мен БІРДЕЙ
# "hardware adapter белсенді емес" статусы) — арна/кілт картасы
# (PacketParser._KEY_MAP["TEMP"]) дайын тұр, тек нақты сенсор қосылмаған.
TEMPERATURE_CHANNEL = SensorChannel(
    key="temperature",
    display_name="Температура",
    unit="°C",
    minimum=-40.0,
    maximum=200.0,
    decimals=1,
)
