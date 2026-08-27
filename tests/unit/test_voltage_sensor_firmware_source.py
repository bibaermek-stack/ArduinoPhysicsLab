"""Voltage Sensor firmware (``voltage_sensor.ino``) source-contract тесттері.

Бұл Python/pytest ортасында Arduino коды компиляцияланбайды/орындалмайды
— сондықтан бұл тесттер firmware мәтінінің өзін (калибрлеу тұрақтылары,
INA226_WE кітапханасы, protocol/debug ажыратылуы, ақаулық өңдеу
паттерндері) тексереді. Мақсат: нақты hardware-де тексерілген калибрлеу
логикасының (``VOLTAGE_CAL``, ``ZERO_THRESHOLD_V``, ``SAMPLE_COUNT``)
firmware мәтінінде сақталуын және production Serial ағынына debug
жолдарының араласпайтынын кепілдендіру.
"""

import re
from pathlib import Path

import pytest

_FIRMWARE_PATH = (
    Path(__file__).resolve().parents[2]
    / "firmware"
    / "voltage_sensor"
    / "voltage_sensor.ino"
)


@pytest.fixture(scope="module")
def firmware_source() -> str:
    return _FIRMWARE_PATH.read_text(encoding="utf-8")


def _strip_comments(source: str) -> str:
    """``/* ... */`` және ``//`` комментарийлерін алып тастайды — "мұнда
    X жоқ" секілді терістеу тексерулері түсіндірме мәтіндегі сөздерге
    жаңылыспау үшін.
    """
    without_block = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", without_block)


@pytest.fixture(scope="module")
def firmware_code(firmware_source: str) -> str:
    return _strip_comments(firmware_source)


# ---- 1. INA226_WE сақталған (Rob Tillaart-тың INA226.h-қа ауыстырылмаған)


def test_ina226_we_library_used(firmware_code: str) -> None:
    assert "#include <INA226_WE.h>" in firmware_code
    assert "INA226_WE ina226" in firmware_code
    assert "#include <INA226.h>" not in firmware_code


def test_uses_get_bus_voltage_v_api(firmware_code: str) -> None:
    assert "ina226.getBusVoltage_V()" in firmware_code
    assert "ina226.init()" in firmware_code


# ---- 2-4. Калибрлеу тұрақтылары сақталған -------------------------------


def test_voltage_cal_constant_preserved(firmware_source: str) -> None:
    assert "const float VOLTAGE_CAL = 1.000;" in firmware_source


def test_sample_count_constant_preserved(firmware_source: str) -> None:
    assert "const uint8_t SAMPLE_COUNT = 20;" in firmware_source


def test_zero_threshold_constant_preserved(firmware_source: str) -> None:
    assert "const float ZERO_THRESHOLD_V = 0.003;" in firmware_source


def test_sampling_uses_five_ms_interval_non_blocking(firmware_source: str, firmware_code: str) -> None:
    assert "const unsigned long SAMPLE_INTERVAL_MS = 5;" in firmware_source
    assert "delay(5)" not in firmware_code
    assert "delay(300)" not in firmware_code


# ---- 5. PC packet calibrated voltage қолданады ---------------------------


def test_measurement_sends_calibrated_voltage_not_raw(firmware_source: str) -> None:
    assert "sendMeasurement(voltage);" in firmware_source
    assert "sendMeasurement(rawVoltage)" not in firmware_source


def test_calibration_steps_present_in_order(firmware_source: str) -> None:
    finalize_match = re.search(
        r"void finalizeMeasurement\(.*?\n\}", firmware_source, re.DOTALL
    )
    assert finalize_match is not None
    body = finalize_match.group(0)

    cal_pos = body.find("rawVoltage * VOLTAGE_CAL")
    threshold_pos = body.find("voltage < ZERO_THRESHOLD_V")
    send_pos = body.find("sendMeasurement(voltage)")

    assert -1 not in (cal_pos, threshold_pos, send_pos)
    assert cal_pos < threshold_pos < send_pos


# ---- 6. Serial baud = 115200 ---------------------------------------------


def test_serial_baud_is_115200(firmware_source: str) -> None:
    assert "Serial.begin(115200);" in firmware_source
    assert "Serial.begin(9600)" not in firmware_source


# ---- 7. production stream-де debug мәтін жоқ -----------------------------


def test_debug_lines_are_compiled_out_by_default(firmware_source: str) -> None:
    assert "#define DEBUG_SERIAL 0" in firmware_source
    assert 'DEBUG_PRINT("Voltage(V): ")' in firmware_source
    assert re.search(r'(?<!DEBUG_)(?<!#define )Serial\.print[a-z]*\("Voltage', firmware_source) is None
    assert re.search(r'(?<!DEBUG_)(?<!#define )Serial\.print[a-z]*\("U = ', firmware_source) is None
    assert re.search(r'(?<!DEBUG_)(?<!#define )Serial\.print[a-z]*\("OLED ERROR', firmware_source) is None
    assert re.search(r'(?<!DEBUG_)(?<!#define )Serial\.print[a-z]*\("INA226 not found', firmware_source) is None


def test_debug_macro_is_noop_when_disabled(firmware_source: str) -> None:
    disabled_block_match = re.search(
        r"#else\s*\n\s*#define DEBUG_PRINT\(\.\.\.\)\s*\n\s*#define DEBUG_PRINTLN\(\.\.\.\)\s*\n#endif",
        firmware_source,
    )
    assert disabled_block_match is not None


# ---- 8. OLED failure protocol-ды тоқтатпайды ------------------------------


def test_no_blocking_infinite_loop_on_sensor_failure(firmware_code: str) -> None:
    assert re.search(r"while\s*\(\s*true\s*\)", firmware_code) is None
    assert re.search(r"while\s*\(\s*1\s*\)", firmware_code) is None


def test_oled_failure_is_guarded_and_non_fatal(firmware_source: str) -> None:
    assert "bool oledReady = false;" in firmware_source
    assert "if (!oledReady) {" in firmware_source
    update_display_match = re.search(
        r"void updateDisplay\(.*?\n\}", firmware_source, re.DOTALL
    )
    assert update_display_match is not None
    assert "return;" in update_display_match.group(0)


# ---- 9. INA226 failure HELLO-ны тоқтатпайды ------------------------------


def test_hello_is_not_gated_by_sensor_readiness(firmware_source: str) -> None:
    send_hello_match = re.search(r"void sendHello\(\).*?\n\}", firmware_source, re.DOTALL)
    assert send_hello_match is not None
    assert "sensorReady" not in send_hello_match.group(0)

    handle_line_match = re.search(r"void handleLine\(.*?\n\}", firmware_source, re.DOTALL)
    assert handle_line_match is not None
    assert re.search(
        r'isHelloCommand\(rawLine\)\)\s*\{\s*\n\s*sendHello\(\);', handle_line_match.group(0)
    )


def test_ina226_missing_only_skips_measurement_not_serial_loop(firmware_source: str) -> None:
    loop_match = re.search(r"void loop\(\) \{.*?\n\}", firmware_source, re.DOTALL)
    assert loop_match is not None
    body = loop_match.group(0)
    assert body.index("readSerialCommands();") < body.index("if (sensorReady)")


# ---- 10. HELLO SENSOR=VOLTAGE дұрыс ---------------------------------------


def test_hello_reports_sensor_voltage(firmware_source: str) -> None:
    # kезeng 30: SRAM түзетуі — идентификация жолдары PROGMEM-де (RAM-ды
    # жемейді), бірақ аттары/мәндері сол қалпы.
    assert 'const char SENSOR_TYPE[] PROGMEM = "VOLTAGE";' in firmware_source
    assert 'const char DEVICE_ID[] PROGMEM = "APL-VOLTAGE-01";' in firmware_source
    assert 'const char CHIP_NAME[] PROGMEM = "INA226";' in firmware_source


# ---- 11. SET_EXP дұрыс -----------------------------------------------------


def test_set_exp_command_and_ack(firmware_source: str) -> None:
    # kезeng 30: SET_EXP_PREFIX PROGMEM-де — strncmp_P() арқылы салыстырылады.
    assert 'strncmp_P(rawLine, SET_EXP_PREFIX, SET_EXP_PREFIX_LEN)' in firmware_source
    assert 'const char SET_EXP_PREFIX[] PROGMEM = "SET_EXP=";' in firmware_source
    assert 'Serial.print(F("OK,EXP="));' in firmware_source


# ---- 12. measurement packet EXP=<id>,U=<value> ---------------------------


def test_measurement_packet_format(firmware_source: str) -> None:
    send_measurement_match = re.search(
        r"void sendMeasurement\(.*?\n\}", firmware_source, re.DOTALL
    )
    assert send_measurement_match is not None
    body = send_measurement_match.group(0)
    # kезeng 30: SRAM түзетуі — хаттама фрагменттері F() арқылы флеште.
    assert 'Serial.print(F("EXP="));' in body
    assert 'Serial.print(currentExperimentId);' in body
    assert 'Serial.print(F(",U="));' in body


def test_boot_default_experiment_id_is_neutral_not_a_real_experiment(
    firmware_source: str,
) -> None:
    # Bug fix (kезeng 26): бұрын "current-voltage" хардкодталған еді
    # (нақты тәжірибе id-і) — Current Sensor firmware-дегі "ohms-law"
    # default-мен дәл сол тапта табылған класс ақауы (SET_EXP жетпесе,
    # кездейсоқ бір тәжірибемен сәйкес келіп қалу). Бос мән ешбір нақты
    # тәжірибемен ешқашан сәйкес келмейді.
    assert 'char currentExperimentId[EXPERIMENT_ID_MAX_LEN] = "";' in firmware_source


def test_boot_default_initializer_is_not_hardcoded_to_a_real_experiment_id(
    firmware_code: str,
) -> None:
    # Дәл boot-default ИНИЦИАЛИЗАТОРЫН тексереді (whitelist массивінде
    # "current-voltage"/"ohms-law" заңды түрде бар болғандықтан, жәй
    # "жол файлда жоқ" деген substring тексеруі енді дұрыс емес).
    assert 'char currentExperimentId[EXPERIMENT_ID_MAX_LEN] = "";' in firmware_code
    assert 'char currentExperimentId[EXPERIMENT_ID_MAX_LEN] = "current-voltage";' not in firmware_code
    assert 'char currentExperimentId[EXPERIMENT_ID_MAX_LEN] = "ohms-law";' not in firmware_code


# ---- kезeng 27: SET_EXP parser bug (ұзын id-лер бос жолға айналатын) ------


def test_no_arduino_string_class_used_for_command_parsing(firmware_code: str) -> None:
    # Root cause: Arduino `String` heap allocation-дары (heap
    # фрагментациясы) ұзын id-лерде silent түрде бос жолға айналатын.
    # Түзету — command parsing толығымен heap-сіз char[]/strcmp-ке көшті.
    assert "String line" not in firmware_code
    assert "String newExperimentId" not in firmware_code
    assert ".substring(" not in firmware_code
    assert ".startsWith(" not in firmware_code
    assert ".equalsIgnoreCase(" not in firmware_code


def test_experiment_id_buffer_fits_longest_supported_id(firmware_source: str) -> None:
    longest_id = max(
        ("current-voltage", "series-connection", "parallel-connection", "current-work-power", "ohms-law"),
        key=len,
    )
    match = re.search(r"const uint8_t EXPERIMENT_ID_MAX_LEN = (\d+);", firmware_source)
    assert match is not None
    max_len = int(match.group(1))
    assert max_len > len(longest_id)


def test_whitelist_contains_exactly_the_five_implemented_ids(firmware_source: str) -> None:
    # kезeng 30: SRAM түзетуі — whitelist енді PROGMEM string table
    # (EXPERIMENT_ID_STR_N жеке тұрақтылары + PROGMEM pointer массиві),
    # бұрынғы inline "SUPPORTED_EXPERIMENT_IDS[] = {...}" литералдары емес.
    ids = set(
        re.findall(r'const char EXPERIMENT_ID_STR_\d\[\] PROGMEM = "([^"]+)";', firmware_source)
    )
    assert ids == {
        "current-voltage",
        "series-connection",
        "parallel-connection",
        "current-work-power",
        "ohms-law",
    }


def test_whitelist_pointer_table_is_progmem(firmware_source: str) -> None:
    assert (
        "const char *const SUPPORTED_EXPERIMENT_IDS[] PROGMEM = {" in firmware_source
    )


def test_unsupported_experiment_never_acked_with_matching_id(firmware_source: str) -> None:
    handle_line_match = re.search(r"void handleLine\(.*?\n\}", firmware_source, re.DOTALL)
    assert handle_line_match is not None
    body = handle_line_match.group(0)
    assert re.search(
        r"if \(isSupportedExperiment\(requestedId\)\) \{\s*\n\s*copyExperimentId\(requestedId\);",
        body,
    )


# ---- kезeng 30: SRAM регрессия түзетуі (OLED бос қалу) --------------------


def test_pgmspace_header_included(firmware_source: str) -> None:
    assert "#include <avr/pgmspace.h>" in firmware_source


def test_is_supported_experiment_uses_progmem_read(firmware_code: str) -> None:
    match = re.search(r"bool isSupportedExperiment\(.*?\n\}", firmware_code, re.DOTALL)
    assert match is not None
    body = match.group(0)
    assert "pgm_read_word(" in body
    assert "strcmp_P(" in body
    assert "strcmp(" not in body  # тек strcmp_P, plain strcmp ЖОҚ


def test_is_hello_command_uses_progmem_read(firmware_code: str) -> None:
    match = re.search(r"bool isHelloCommand\(.*?\n\}", firmware_code, re.DOTALL)
    assert match is not None
    body = match.group(0)
    assert "PROGMEM" in body
    assert "pgm_read_byte(" in body


def test_oled_title_uses_flash_string_helper(firmware_source: str) -> None:
    # "KERNEU SENSOR" екі жерде де (setup() + updateDisplay()) F()-пен
    # флеште — RAM-ды екі есе жаппайды.
    assert firmware_source.count('display.println(F("KERNEU SENSOR"));') == 2


def test_oled_unit_suffix_uses_flash_string_helper(firmware_source: str) -> None:
    assert 'display.println(F(" V"));' in firmware_source


def test_debug_free_ram_instrumentation_is_compile_time_guarded(firmware_source: str) -> None:
    assert "#define DEBUG_FREE_RAM 0" in firmware_source
    guarded_match = re.search(
        r"#if DEBUG_FREE_RAM\s*\nint getFreeRamBytes\(\)", firmware_source
    )
    assert guarded_match is not None


def test_free_ram_helper_not_compiled_when_debug_disabled(firmware_code: str) -> None:
    # firmware_code — комментарийлер алынған мәтін ғана, #if/#endif
    # preprocessor-ды НАҚТЫ орындамайды — сондықтан бұл тест getFreeRamBytes()
    # анықтамасының #if DEBUG_FREE_RAM блогының ІШІНДЕ екенін тексереді
    # (compile-time guard дұрыс орналасқанын растау), нақты preprocessing
    # емес.
    define_pos = firmware_code.find("#define DEBUG_FREE_RAM 0")
    guard_pos = firmware_code.find("#if DEBUG_FREE_RAM")
    func_pos = firmware_code.find("int getFreeRamBytes()")
    endif_pos = firmware_code.find("#endif", guard_pos)
    assert -1 not in (define_pos, guard_pos, func_pos, endif_pos)
    assert guard_pos < func_pos < endif_pos


def test_line_buffer_still_fits_longest_real_command(firmware_source: str) -> None:
    longest_command = "SET_EXP=parallel-connection"
    match = re.search(r"const size_t LINE_BUFFER_SIZE = (\d+);", firmware_source)
    assert match is not None
    buffer_size = int(match.group(1))
    assert buffer_size > len(longest_command)  # '\0' үшін де орын


def test_display_display_called_after_finalized_measurement(firmware_source: str) -> None:
    update_display_match = re.search(r"void updateDisplay\(.*?\n\}", firmware_source, re.DOTALL)
    assert update_display_match is not None
    body = update_display_match.group(0)
    assert "display.display();" in body

    finalize_match = re.search(r"void finalizeMeasurement\(.*?\n\}", firmware_source, re.DOTALL)
    assert finalize_match is not None
    assert "updateDisplay(voltage);" in finalize_match.group(0)


def test_identification_constants_are_progmem(firmware_source: str) -> None:
    assert 'const char MODEL[] PROGMEM = "V1";' in firmware_source
    assert 'const char FIRMWARE_VERSION[] PROGMEM = "1.0";' in firmware_source


def test_send_hello_reads_identification_constants_from_flash(firmware_source: str) -> None:
    send_hello_match = re.search(r"void sendHello\(\).*?\n\}", firmware_source, re.DOTALL)
    assert send_hello_match is not None
    body = send_hello_match.group(0)
    for name in ("DEVICE_ID", "MODEL", "SENSOR_TYPE", "CHIP_NAME", "FIRMWARE_VERSION"):
        assert f"(const __FlashStringHelper *){name}" in body


def test_calibration_and_averaging_untouched_by_sram_fix(firmware_source: str) -> None:
    # SRAM түзетуі есептеу/калибрлеу логикасына мүлде тимегенін растайды.
    assert "const float VOLTAGE_CAL = 1.000;" in firmware_source
    assert "const float ZERO_THRESHOLD_V = 0.003;" in firmware_source
    assert "const uint8_t SAMPLE_COUNT = 20;" in firmware_source
    assert "float voltage = rawVoltage * VOLTAGE_CAL;" in firmware_source
