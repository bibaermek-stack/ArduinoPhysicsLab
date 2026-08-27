"""packet_parser юнит-тесттері.

TODO: docs/serial_protocol.md-те анықталатын пакет форматына сай толық
парсинг тесттерін жазу (бұл файл әзірге тек Phase 38B-де қосылған жаңа
``TEMP=`` кілт картасын тексереді).
"""

from infrastructure.serial_comm.packet_parser import PacketParser


def test_temp_key_maps_to_temperature_channel() -> None:
    # Phase 38B: docs/serial_protocol.md §10-де алдын ала жоспарланған
    # кеңейту нүктесі — Metal-resistance-temperature (№8) үшін.
    parser = PacketParser()

    result = parser.parse_line("EXP=metal-resistance-temperature,U=5.0,I=0.2,TEMP=23.4")

    assert result.is_valid is True
    assert result.values["temperature"] == 23.4
    assert result.values["voltage"] == 5.0
    assert result.values["current"] == 0.2
    assert result.warnings == ()
