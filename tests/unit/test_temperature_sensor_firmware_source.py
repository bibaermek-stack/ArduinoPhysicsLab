"""Temperature Sensor firmware (``temperature_sensor.ino``) source-contract
тесттері.

Voltage/Current Sensor firmware-мен бірдей ұстаным: Python/pytest
ортасында Arduino коды компиляцияланбайды/орындалмайды — бұл тесттер
firmware мәтінінің өзін (protocol/debug ажыратылуы, non-blocking
conversion state machine, ақаулық өңдеу паттерндері) тексереді.

**Ескерту**: бұл firmware НАҚТЫ DS18B20 hardware-де әлі тексерілмеген
(§firmware/temperature_sensor/README.md) — Voltage/Current Sensor
firmware-дегі "ВАЛИДТЕЛГЕН КАЛИБРЛЕУ" статусына ие ЕМЕС. Бұл тесттер
тек кодтың ӨЗІНІҢ protocol/SRAM/non-blocking конвенцияларға сай
екенін растайды, нақты сенсормен физикалық дұрыстығын емес.
"""

import re
from pathlib import Path

import pytest

_FIRMWARE_PATH = (
    Path(__file__).resolve().parents[2]
    / "firmware"
    / "temperature_sensor"
    / "temperature_sensor.ino"
)


@pytest.fixture(scope="module")
def firmware_source() -> str:
    return _FIRMWARE_PATH.read_text(encoding="utf-8")


def _strip_comments(source: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", without_block)


@pytest.fixture(scope="module")
def firmware_code(firmware_source: str) -> str:
    return _strip_comments(firmware_source)


# ---- Идентификация (HELLO handshake) --------------------------------------


def test_hello_reports_sensor_temperature(firmware_source: str) -> None:
    assert 'const char SENSOR_TYPE[] PROGMEM = "TEMPERATURE";' in firmware_source
    assert 'const char DEVICE_ID[] PROGMEM = "APL-TEMPERATURE-01";' in firmware_source
    assert 'const char CHIP_NAME[] PROGMEM = "DS18B20";' in firmware_source


def test_send_hello_reads_identification_constants_from_flash(firmware_source: str) -> None:
    send_hello_match = re.search(r"void sendHello\(\).*?\n\}", firmware_source, re.DOTALL)
    assert send_hello_match is not None
    body = send_hello_match.group(0)
    for name in ("DEVICE_ID", "MODEL", "SENSOR_TYPE", "CHIP_NAME", "FIRMWARE_VERSION"):
        assert f"(const __FlashStringHelper *){name}" in body


def test_hello_is_not_gated_by_sensor_readiness(firmware_source: str) -> None:
    send_hello_match = re.search(r"void sendHello\(\).*?\n\}", firmware_source, re.DOTALL)
    assert send_hello_match is not None
    assert "sensorReady" not in send_hello_match.group(0)

    handle_line_match = re.search(r"void handleLine\(.*?\n\}", firmware_source, re.DOTALL)
    assert handle_line_match is not None
    assert re.search(
        r'isHelloCommand\(rawLine\)\)\s*\{\s*\n\s*sendHello\(\);', handle_line_match.group(0)
    )


# ---- Measurement packet format ---------------------------------------------


def test_measurement_packet_uses_temp_key(firmware_source: str) -> None:
    send_measurement_match = re.search(
        r"void sendMeasurement\(.*?\n\}", firmware_source, re.DOTALL
    )
    assert send_measurement_match is not None
    body = send_measurement_match.group(0)
    assert 'Serial.print(F("EXP="));' in body
    assert 'Serial.print(currentExperimentId);' in body
    assert 'Serial.print(F(",TEMP="));' in body


# ---- DS18B20 disconnected/sentinel filtering -------------------------------


def test_device_disconnected_sentinel_is_filtered(firmware_source: str) -> None:
    finalize_match = re.search(r"void finalizeMeasurement\(.*?\n\}", firmware_source, re.DOTALL)
    assert finalize_match is not None
    body = finalize_match.group(0)
    assert "DEVICE_DISCONNECTED_C" in body
    assert "return;" in body


# ---- Non-blocking conversion (no delay() blocking Serial) -----------------


def test_no_blocking_delay_for_conversion(firmware_code: str) -> None:
    # DS18B20-дың ~750 ms conversion уақыты delay() арқылы емес, millis()
    # негізді state machine арқылы күтілуі керек (Voltage/Current Sensor-
    # дегі collectSampleIfDue()-мен бірдей архитектуралық принцип).
    assert "delay(750)" not in firmware_code
    assert re.search(r"while\s*\(\s*true\s*\)", firmware_code) is None
    assert re.search(r"while\s*\(\s*1\s*\)", firmware_code) is None


def test_wait_for_conversion_disabled_for_async_request(firmware_source: str) -> None:
    # setWaitForConversion(false) болмаса, DallasTemperature кітапханасы
    # requestTemperatures() ІШІНДЕ өзі delay()-мен блоктайды — non-blocking
    # дизайнның негізгі алғышарты.
    assert "sensors.setWaitForConversion(false);" in firmware_source


def test_conversion_state_machine_uses_millis_not_delay(firmware_source: str) -> None:
    assert "conversionStartMillis = millis();" in firmware_source
    assert "conversionPending" in firmware_source
    assert "CONVERSION_WAIT_MS" in firmware_source


def test_loop_reads_serial_before_checking_sensor(firmware_source: str) -> None:
    loop_match = re.search(r"void loop\(\) \{.*?\n\}", firmware_source, re.DOTALL)
    assert loop_match is not None
    body = loop_match.group(0)
    assert body.index("readSerialCommands();") < body.index("if (sensorReady)")


# ---- Serial baud / debug guarding (parity with Voltage/Current Sensor) ----


def test_serial_baud_is_115200(firmware_source: str) -> None:
    assert "Serial.begin(115200);" in firmware_source


def test_debug_lines_are_compiled_out_by_default(firmware_source: str) -> None:
    assert "#define DEBUG_SERIAL 0" in firmware_source


# ---- SET_EXP whitelist: тек metal-resistance-temperature ------------------


def test_whitelist_contains_both_temperature_experiments(firmware_source: str) -> None:
    # kезeng 39B: compare-heat-quantity (жылу №1) қосылды —
    # metal-resistance-temperature-мен (электр №8) қатар.
    ids = set(
        re.findall(r'const char EXPERIMENT_ID_STR_\d\[\] PROGMEM = "([^"]+)";', firmware_source)
    )
    assert ids == {"metal-resistance-temperature", "compare-heat-quantity"}


def test_experiment_id_buffer_fits_the_longest_temperature_experiment_id(
    firmware_source: str,
) -> None:
    longest_id = max(("metal-resistance-temperature", "compare-heat-quantity"), key=len)
    match = re.search(r"const uint8_t EXPERIMENT_ID_MAX_LEN = (\d+);", firmware_source)
    assert match is not None
    max_len = int(match.group(1))
    assert max_len > len(longest_id)


def test_boot_default_experiment_id_is_neutral(firmware_source: str) -> None:
    assert 'char currentExperimentId[EXPERIMENT_ID_MAX_LEN] = "";' in firmware_source


def test_unsupported_experiment_never_acked_with_matching_id(firmware_source: str) -> None:
    handle_line_match = re.search(r"void handleLine\(.*?\n\}", firmware_source, re.DOTALL)
    assert handle_line_match is not None
    body = handle_line_match.group(0)
    assert re.search(
        r"if \(isSupportedExperiment\(requestedId\)\) \{\s*\n\s*copyExperimentId\(requestedId\);",
        body,
    )


# ---- No Arduino String class (heap-free parsing, project-wide convention) -


def test_no_arduino_string_class_used_for_command_parsing(firmware_code: str) -> None:
    assert "String line" not in firmware_code
    assert "String newExperimentId" not in firmware_code
    assert ".substring(" not in firmware_code
    assert ".startsWith(" not in firmware_code
    assert ".equalsIgnoreCase(" not in firmware_code


# ---- PROGMEM / SRAM parity with Voltage/Current Sensor ---------------------


def test_pgmspace_header_included(firmware_source: str) -> None:
    assert "#include <avr/pgmspace.h>" in firmware_source


def test_is_supported_experiment_uses_progmem_read(firmware_code: str) -> None:
    match = re.search(r"bool isSupportedExperiment\(.*?\n\}", firmware_code, re.DOTALL)
    assert match is not None
    body = match.group(0)
    assert "pgm_read_word(" in body
    assert "strcmp_P(" in body
    assert "strcmp(" not in body


def test_identification_constants_are_progmem(firmware_source: str) -> None:
    assert 'const char MODEL[] PROGMEM = "V1";' in firmware_source
    assert 'const char FIRMWARE_VERSION[] PROGMEM = "1.0";' in firmware_source


# ---- OLED failure is non-fatal (parity) ------------------------------------


def test_oled_failure_is_guarded_and_non_fatal(firmware_source: str) -> None:
    assert "bool oledReady = false;" in firmware_source
    update_display_match = re.search(
        r"void updateDisplay\(.*?\n\}", firmware_source, re.DOTALL
    )
    assert update_display_match is not None
    assert "if (!oledReady) {" in update_display_match.group(0)
    assert "return;" in update_display_match.group(0)


# ---- Libraries ---------------------------------------------------------------


def test_uses_onewire_and_dallastemperature_libraries(firmware_source: str) -> None:
    assert "#include <OneWire.h>" in firmware_source
    assert "#include <DallasTemperature.h>" in firmware_source
    assert "OneWire oneWire(ONE_WIRE_PIN);" in firmware_source
    assert "DallasTemperature sensors(&oneWire);" in firmware_source
