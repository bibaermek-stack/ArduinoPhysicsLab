"""Current Sensor firmware (``current_sensor.ino``) source-contract тесттері.

Бұл Python/pytest ортасында Arduino коды компиляцияланбайды/орындалмайды
— сондықтан бұл тесттер firmware мәтінінің өзін (калибрлеу тұрақтылары,
protocol/debug ажыратылуы, ақаулық өңдеу паттерндері) тексереді. Мақсат:
Vernier reference-пен валидтелген калибрлеу логикасының (``CURRENT_CAL``,
``ZERO_THRESHOLD_mA``, ``SAMPLE_COUNT``) firmware мәтінінде сақталуын және
production Serial ағынына debug жолдарының араласпайтынын кепілдендіру.
"""

import re
from pathlib import Path

import pytest

_FIRMWARE_PATH = (
    Path(__file__).resolve().parents[2]
    / "firmware"
    / "current_sensor"
    / "current_sensor.ino"
)


@pytest.fixture(scope="module")
def firmware_source() -> str:
    return _FIRMWARE_PATH.read_text(encoding="utf-8")


def _strip_comments(source: str) -> str:
    """``/* ... */`` және ``//`` комментарийлерін алып тастайды — "мұнда
    X жоқ" секілді терістеу тексерулері түсіндірме мәтіндегі сөздерге
    (мыс. "delay(5) арқылы емес") жаңылыспау үшін.
    """
    without_block = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", without_block)


@pytest.fixture(scope="module")
def firmware_code(firmware_source: str) -> str:
    return _strip_comments(firmware_source)


# ---- 1-3. Калибрлеу тұрақтылары сақталған -------------------------------


def test_current_cal_constant_preserved(firmware_source: str) -> None:
    assert "const float CURRENT_CAL = 0.915;" in firmware_source


def test_zero_threshold_constant_preserved(firmware_source: str) -> None:
    assert "const float ZERO_THRESHOLD_mA = 0.5;" in firmware_source


def test_sample_count_constant_preserved(firmware_source: str) -> None:
    assert "const uint8_t SAMPLE_COUNT = 20;" in firmware_source


# ---- 4. Measurement packet calibrated current қолданады ------------------


def test_measurement_sends_calibrated_current_not_raw(firmware_source: str) -> None:
    # sendMeasurement() калибрленген current_A-мен шақырылады.
    assert "sendMeasurement(current_A);" in firmware_source
    # Raw (калибрленбеген) мән ешқашан тікелей жіберілмейді.
    assert "sendMeasurement(rawCurrent_A)" not in firmware_source
    assert re.search(r'Serial\.print[a-z]*\("I="\);?\s*Serial\.print[a-z]*\(rawCurrent', firmware_source) is None


def test_calibration_eight_steps_present_in_order(firmware_source: str) -> None:
    # 8-қадамдық калибрлеу тізбегі (абсолют мән -> mA -> CURRENT_CAL ->
    # zero-threshold -> A) дәл сол ретте кодта болуы керек.
    finalize_match = re.search(
        r"void finalizeMeasurement\(.*?\n\}", firmware_source, re.DOTALL
    )
    assert finalize_match is not None
    body = finalize_match.group(0)

    fabs_pos = body.find("fabs(rawCurrent_A)")
    ma_pos = body.find("rawCurrent_A * 1000.0")
    cal_pos = body.find("rawCurrent_mA * CURRENT_CAL")
    threshold_pos = body.find("current_mA < ZERO_THRESHOLD_mA")
    back_to_a_pos = body.find("current_mA / 1000.0")

    assert -1 not in (fabs_pos, ma_pos, cal_pos, threshold_pos, back_to_a_pos)
    assert fabs_pos < ma_pos < cal_pos < threshold_pos < back_to_a_pos


def test_sampling_uses_five_ms_interval_and_ina226_getcurrent(
    firmware_source: str, firmware_code: str
) -> None:
    assert "const unsigned long SAMPLE_INTERVAL_MS = 5;" in firmware_source
    assert "ina226.getCurrent()" in firmware_source
    # Delay-негізді (blocking) sampling firmware КОДЫНДА (комментарийден
    # тыс) болмауы керек.
    assert "delay(5)" not in firmware_code
    assert "delay(300)" not in firmware_code


# ---- 5. Serial baud = 115200 ---------------------------------------------


def test_serial_baud_is_115200(firmware_source: str) -> None:
    assert "Serial.begin(115200);" in firmware_source
    assert "Serial.begin(9600)" not in firmware_source


# ---- 6. Debug жолдары production protocol-ға араласпайды ----------------


def test_debug_lines_are_compiled_out_by_default(firmware_source: str) -> None:
    assert "#define DEBUG_SERIAL 0" in firmware_source
    # "Raw:"/"Current:" тек DEBUG_PRINT(...)/DEBUG_PRINTLN(...) макросы
    # арқылы шығарылады — production Serial.print/println-мен тікелей емес.
    assert 'DEBUG_PRINT("Raw: ")' in firmware_source
    assert 'DEBUG_PRINT("Current: ")' in firmware_source
    assert re.search(r'(?<!DEBUG_)(?<!#define )Serial\.print[a-z]*\("Raw', firmware_source) is None
    assert re.search(r'(?<!DEBUG_)(?<!#define )Serial\.print[a-z]*\("Current:', firmware_source) is None


def test_debug_macro_is_noop_when_disabled(firmware_source: str) -> None:
    # DEBUG_SERIAL=0 болғанда DEBUG_PRINT/DEBUG_PRINTLN бос макроға
    # ауысады (толық compile-out) — production Serial ағынына ешқандай
    # debug байты қосылмайды.
    disabled_block_match = re.search(
        r"#else\s*\n\s*#define DEBUG_PRINT\(\.\.\.\)\s*\n\s*#define DEBUG_PRINTLN\(\.\.\.\)\s*\n#endif",
        firmware_source,
    )
    assert disabled_block_match is not None


# ---- 7. OLED failure protocol-ды тоқтатпайды ------------------------------


def test_no_blocking_infinite_loop_on_sensor_failure(firmware_code: str) -> None:
    # Ескі "while(true)" секілді толық тоқтататын паттерн КОДТА жоқ
    # (тек түсіндірме комментарийде "ескіде осылай болатын" деп аталады).
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


# ---- 8. INA226 failure HELLO-ны тоқтатпайды ------------------------------


def test_hello_is_not_gated_by_sensor_readiness(firmware_source: str) -> None:
    send_hello_match = re.search(r"void sendHello\(\).*?\n\}", firmware_source, re.DOTALL)
    assert send_hello_match is not None
    assert "sensorReady" not in send_hello_match.group(0)

    handle_line_match = re.search(r"void handleLine\(.*?\n\}", firmware_source, re.DOTALL)
    assert handle_line_match is not None
    # HELLO? командасы sensorReady шартынсыз sendHello()-ды шақырады.
    assert re.search(
        r'isHelloCommand\(rawLine\)\)\s*\{\s*\n\s*sendHello\(\);', handle_line_match.group(0)
    )


def test_ina226_missing_only_skips_measurement_not_serial_loop(firmware_source: str) -> None:
    loop_match = re.search(r"void loop\(\) \{.*?\n\}", firmware_source, re.DOTALL)
    assert loop_match is not None
    body = loop_match.group(0)

    # readSerialCommands() sensorReady шартынан бұрын, шартсыз шақырылады.
    assert body.index("readSerialCommands();") < body.index("if (sensorReady)")


# ---- Қосымша: жоқ кітапхана әдісі (setMaxCurrentShunt) қосылмаған --------


def test_set_max_current_shunt_not_used(firmware_code: str) -> None:
    # Пайдаланушының нақты кітапхана нұсқасында бұл әдіс жоқ — firmware
    # оны КОДТА шақырмауы керек (комментарийде "неге қолданылмайды" деп
    # түсіндіріледі, бұл рұқсат етіледі), калибрлеу толығымен
    # CURRENT_CAL арқылы жасалады.
    assert "setMaxCurrentShunt" not in firmware_code


# ---- Қосымша: OLED/INA226 конфигурациясы дұрыс ----------------------------


def test_oled_and_ina226_addresses_and_libraries(firmware_source: str) -> None:
    assert "#include <Adafruit_GFX.h>" in firmware_source
    assert "#include <Adafruit_SSD1306.h>" in firmware_source
    assert "#include <INA226.h>" in firmware_source
    assert "INA226 ina226(0x40);" in firmware_source
    assert 'display.begin(SSD1306_SWITCHCAPVCC, 0x3C)' in firmware_source


def test_oled_shows_label_and_unit_switch_at_1000ma(firmware_source: str) -> None:
    update_display_match = re.search(
        r"void updateDisplay\(.*?\n\}", firmware_source, re.DOTALL
    )
    assert update_display_match is not None
    body = update_display_match.group(0)
    assert '"TOK SENSORY"' in body
    assert "current_mA < 1000.0" in body
    assert '" mA"' in body
    assert '" A"' in body


# ---- SET_EXP / multi-experiment switching (нақты hardware bug fix) --------


def test_set_exp_command_and_ack(firmware_source: str) -> None:
    # kезeng 30 паритеті: SET_EXP_PREFIX PROGMEM-де — strncmp_P() арқылы
    # салыстырылады.
    assert 'strncmp_P(rawLine, SET_EXP_PREFIX, SET_EXP_PREFIX_LEN)' in firmware_source
    assert 'const char SET_EXP_PREFIX[] PROGMEM = "SET_EXP=";' in firmware_source
    assert 'Serial.print(F("OK,EXP="));' in firmware_source


def test_measurement_packet_format(firmware_source: str) -> None:
    send_measurement_match = re.search(
        r"void sendMeasurement\(.*?\n\}", firmware_source, re.DOTALL
    )
    assert send_measurement_match is not None
    body = send_measurement_match.group(0)
    # kезeng 30 паритеті: хаттама фрагменттері F() арқылы флеште.
    assert 'Serial.print(F("EXP="));' in body
    assert 'Serial.print(currentExperimentId);' in body
    assert 'Serial.print(F(",I="));' in body


def test_boot_default_experiment_id_is_neutral_not_a_real_experiment() -> None:
    # Bug fix (kезeng 26): бұрын "ohms-law" хардкодталған еді (нақты
    # тәжірибе id-і) — SET_EXP жазуы осы датчикке жетпесе, ohms-law
    # сұралғанда СӘЙКЕС КЕЛІП қалатын silent ақау болатын (басқа
    # тәжірибелер әрдайым mismatch болатын). Бос мән ешбір нақты
    # тәжірибемен ешқашан сәйкес келмейді.
    assert (
        'char currentExperimentId[EXPERIMENT_ID_MAX_LEN] = "";'
        in _FIRMWARE_PATH.read_text(encoding="utf-8")
    )


def test_boot_default_initializer_is_not_hardcoded_to_a_real_experiment_id(
    firmware_code: str,
) -> None:
    # Дәл boot-default ИНИЦИАЛИЗАТОРЫН тексереді (whitelist массивінде
    # "ohms-law" заңды түрде бар болғандықтан, жәй "жол файлда жоқ" деген
    # substring тексеруі енді дұрыс емес).
    assert 'char currentExperimentId[EXPERIMENT_ID_MAX_LEN] = "";' in firmware_code
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
    assert max_len > len(longest_id)  # null terminator + headroom үшін де орын жеткілікті


def test_whitelist_contains_exactly_the_five_implemented_ids(firmware_source: str) -> None:
    # kезeng 30 паритеті: whitelist енді PROGMEM string table
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
    # copyExperimentId() тек isSupportedExperiment() шарты ІШІНДЕ шақырылады
    # — support етілмейтін id currentExperimentId-ды ЕШҚАШАН өзгертпейді.
    assert re.search(
        r"if \(isSupportedExperiment\(requestedId\)\) \{\s*\n\s*copyExperimentId\(requestedId\);",
        body,
    )


# ---- kезeng 30 паритеті: SRAM регрессиясының алдын алу (Voltage Sensor
# firmware-де табылған ақаумен бірдей архитектуралық қауіп) ----------------


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


def test_hello_reports_sensor_current(firmware_source: str) -> None:
    # kезeng 30 паритеті: идентификация жолдары PROGMEM-де (RAM-ды
    # жемейді), бірақ аттары/мәндері сол қалпы.
    assert 'const char SENSOR_TYPE[] PROGMEM = "CURRENT";' in firmware_source
    assert 'const char DEVICE_ID[] PROGMEM = "APL-CURRENT-01";' in firmware_source
    assert 'const char CHIP_NAME[] PROGMEM = "INA226";' in firmware_source


def test_identification_constants_are_progmem(firmware_source: str) -> None:
    assert 'const char MODEL[] PROGMEM = "V1";' in firmware_source
    assert 'const char FIRMWARE_VERSION[] PROGMEM = "1.0";' in firmware_source


def test_send_hello_reads_identification_constants_from_flash(firmware_source: str) -> None:
    send_hello_match = re.search(r"void sendHello\(\).*?\n\}", firmware_source, re.DOTALL)
    assert send_hello_match is not None
    body = send_hello_match.group(0)
    for name in ("DEVICE_ID", "MODEL", "SENSOR_TYPE", "CHIP_NAME", "FIRMWARE_VERSION"):
        assert f"(const __FlashStringHelper *){name}" in body


def test_oled_title_uses_flash_string_helper(firmware_source: str) -> None:
    # "TOK SENSORY" екі жерде де (setup() + updateDisplay()) F()-пен
    # флеште — RAM-ды екі есе жаппайды.
    assert firmware_source.count('display.println(F("TOK SENSORY"));') == 2


def test_oled_unit_suffixes_use_flash_string_helper(firmware_source: str) -> None:
    # Current Sensor Voltage Sensor-ден өзгеше — екі бірлік суффиксі бар
    # (mA/A ауысу шегі 1000 mA-де), екеуі де F()-пен флеште болуы керек.
    assert 'display.println(F(" mA"));' in firmware_source
    assert 'display.println(F(" A"));' in firmware_source


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


def test_display_display_called_after_finalized_measurement(firmware_source: str) -> None:
    update_display_match = re.search(r"void updateDisplay\(.*?\n\}", firmware_source, re.DOTALL)
    assert update_display_match is not None
    body = update_display_match.group(0)
    assert "display.display();" in body

    finalize_match = re.search(r"void finalizeMeasurement\(.*?\n\}", firmware_source, re.DOTALL)
    assert finalize_match is not None
    assert "updateDisplay(current_mA);" in finalize_match.group(0)


def test_calibration_and_averaging_untouched_by_sram_fix(firmware_source: str) -> None:
    # SRAM түзетуі есептеу/калибрлеу логикасына мүлде тимегенін растайды.
    assert "const float CURRENT_CAL = 0.915;" in firmware_source
    assert "const float ZERO_THRESHOLD_mA = 0.5;" in firmware_source
    assert "const uint8_t SAMPLE_COUNT = 20;" in firmware_source
    assert "float rawCurrent_mA = rawCurrent_A * 1000.0;" in firmware_source
    assert "float current_mA = rawCurrent_mA * CURRENT_CAL;" in firmware_source
