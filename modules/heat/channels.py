"""Жылу құбылыстары тәжірибелерінің ортақ SensorChannel анықтамалары.

Электр модуліндегі ``modules/electricity/channels.py``-мен бірдей
конвенция: әр модуль өз арналарын осында анықтайды. ``key="temperature"``
электр модуліндегі ``TEMPERATURE_CHANNEL``-мен ӘДЕЙІ бірдей — Arduino
протоколы (``PacketParser._KEY_MAP["TEMP"] = "temperature"``) модульге
тәуелсіз, глобал; екі модуль де сол бір "TEMP=" кілтін жіберетін
физикалық сенсорды (``firmware/temperature_sensor/``) қайта пайдаланады.
"""

from domain.entities.sensor_channel import SensorChannel

# Диапазон электр модуліндегі TEMPERATURE_CHANNEL-ден (-40..200°C, металл
# қыздыру үшін) АЗДАП тар — су/мұзбен жұмыс істейтін жылу тәжірибелеріне
# сай (-10..150°C: мұздың балқуынан суды қайнатуға дейін жеткілікті қор).
TEMPERATURE_CHANNEL = SensorChannel(
    key="temperature",
    display_name="Температура",
    unit="°C",
    minimum=-10.0,
    maximum=150.0,
    decimals=1,
)
