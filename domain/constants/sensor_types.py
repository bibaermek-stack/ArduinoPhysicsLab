"""sensor_types — Arduino Physics Lab-та қолдау көрсетілетін бастапқы
сенсор түрлерінің тұрақтылары.

Бұл тізім тек анықтамалық сипатта: HELLO пакетіндегі белгісіз ``SENSOR``
мәні қате емес, тек ескерту тудырады (``ConnectedDevice`` бәрібір жасалады).
"""

VOLTAGE = "VOLTAGE"
CURRENT = "CURRENT"
ENERGY = "ENERGY"
OHMMETER = "OHMMETER"
TEMPERATURE = "TEMPERATURE"

KNOWN_SENSOR_TYPES: frozenset[str] = frozenset(
    {VOLTAGE, CURRENT, ENERGY, OHMMETER, TEMPERATURE}
)
