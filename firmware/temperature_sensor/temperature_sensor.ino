/*
  Temperature Sensor — Arduino Physics Lab firmware

  Құрылғы: APL-TEMPERATURE-01 (SENSOR=TEMPERATURE)
  Board:   Arduino Nano / Uno (ATmega328P, 16 MHz, 5V логика).
           *** BOARD-SPECIFIC ***
           Voltage/Current Sensor firmware-мен бірдей baseline
           (Nano/Uno), бірақ I2C ЕМЕС — DS18B20 1-Wire шинасы.

  Sensor:  DS18B20 (1-Wire, сандық, зауытта калибрленген ~±0.5°C).
  OLED:    SSD1306 128x64 (I2C, address 0x3C) — Voltage/Current Sensor
           firmware-мен бірдей, қосымша (табылмаса measurement-ге
           әсер етпейді).
  Library: "OneWire" by Paul Stoffregen, "DallasTemperature" by Miles
           Burton, "Adafruit GFX Library", "Adafruit SSD1306" (барлығы
           Arduino Library Manager арқылы орнатылады).

  Сым қосу (wiring):
    DS18B20 GND  -> Arduino GND
    DS18B20 VDD  -> Arduino 5V
    DS18B20 DATA -> Arduino D2  (+ 4.7 kΩ pull-up резисторы DATA-VDD
                    арасында — DS18B20 datasheet стандарт талабы,
                    board-та жоқ, сыртта қосылады)
    OLED SDA/SCL -> Arduino A4/A5 (Voltage/Current Sensor-мен бірдей)

  ================================================================
  DS18B20 — INA226-дан ПРИНЦИПТІ айырмашылық (калибрлеу ЖОҚ, уақыт БАР):
  ================================================================
  INA226 (Voltage/Current Sensor) — I2C арқылы лезде оқылатын analog-
  digital converter, сондықтан 20×5мс "sample average" калибрлеу
  қажет болды. DS18B20 — өзінің ішінде дайын сандық сенсор:
    - Зауытта калибрленген (±0.5°C, -10..+85°C аралығында) — қосымша
      сызықтық/Steinhart-Hart калибрлеу коэффициенті КЕРЕК ЕМЕС, кез
      келген "TEMP_CAL" тұрақтысы жалған дәлдік болар еді.
    - Бірақ conversion (өлшеу) УАҚЫТ алады: 12-bit ажыратымдылықта
      ~750 ms (DS18B20 datasheet). Бұл INA226-ден 100х баяу.
  Сондықтан бұл жерде "sample averaging" емес, "non-blocking conversion
  wait" state machine қолданылады — requestTemperatures() шақырылады,
  содан кейін ЕШБІР delay() ЖОҚ, тек "750 ms өтті ме" тексерісі
  (Voltage/Current Sensor-дегі collectSampleIfDue()-мен бірдей
  архитектуралық принцип: loop() әр айналымда Serial-ды бірден оқиды).

  Тәжірибенің өзі де (metal-resistance-temperature, graph_capture_
  mode="manual") жылдам ағынды емес, "температура тұрақталғанша
  күтіп, содан кейін нүктені қолмен сақтау" жұмысына арналған —
  сондықтан ~1 Hz жаңарту жылдамдығы физикалық тұрғыда да жеткілікті
  (металл сым температурасы миллисекундпен өзгермейді).

  ================================================================
  Протокол: docs/serial_protocol.md (4, 10, 11, 12, 13-бөлімдер):
  ================================================================

    PC  -> "HELLO?"
    Ard -> "TYPE=HELLO,DEV=APL-TEMPERATURE-01,MODEL=V1,SENSOR=TEMPERATURE,CHIP=DS18B20,FW=1.0"

    PC  -> "SET_EXP=<experiment-id>"
    Ard -> "OK,EXP=<experiment-id>"

    Ard -> "EXP=<experiment-id>,TEMP=<celsius>"     (~1 Hz)

  Ақаулық өңдеу:
  - DS18B20 табылмаса: measurement жіберілмейді, бірақ HELLO/SET_EXP
    Serial командалары әдеттегідей жұмыс істей береді (Voltage/Current
    Sensor-мен бірдей ұстаным — while(true) секілді толық тоқтату ЖОҚ).
  - OLED табылмаса: экран жаңартылмайды, sensor/protocol жұмысына
    мүлде әсер етпейді.

  Multi-device: бұл firmware ЕКІ тәжірибеге қатысады (whitelist-те
  екеуі де бар):
  - "metal-resistance-temperature" (электр модулі №8) — Voltage/Current
    Sensor-мен БІРГЕ, үш бөлек физикалық Arduino ретінде жұмыс істейді
    (MultiSensorExperimentCoordinator/ChannelAggregator,
    docs/serial_protocol.md §13). Сол себепті Voltage/Current Sensor
    firmware-нің whitelist-іне де "metal-resistance-temperature"
    қосылды (firmware/voltage_sensor/voltage_sensor.ino,
    firmware/current_sensor/current_sensor.ino) — әйтпесе PC осы
    тәжірибені бастағанда сол екі Arduino SET_EXP-ті қабылдамай, U=/I=
    жіберуді тоқтатар еді.
  - "compare-heat-quantity" (жылу модулі №1, kезeng 39B) — ЖАЛҒЫЗ осы
    Arduino (required_sensor_types=("TEMPERATURE",), бір-құрылғылы
    ExperimentController pipeline-і, coordinator қажет емес).
*/

#include <OneWire.h>
#include <DallasTemperature.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <string.h>
#include <avr/pgmspace.h>

// ---- Debug (production-да өшірулі — тек локал тестілеуге 1 етіп қосыңыз)
#define DEBUG_SERIAL 0

#if DEBUG_SERIAL
  #define DEBUG_PRINT(...) Serial.print(__VA_ARGS__)
  #define DEBUG_PRINTLN(...) Serial.println(__VA_ARGS__)
#else
  #define DEBUG_PRINT(...)
  #define DEBUG_PRINTLN(...)
#endif

// ---- Құрылғы идентификациясы (HELLO handshake, өзгермейді) -----------
// PROGMEM — Voltage/Current Sensor firmware-дегі SRAM түзетуімен бірдей
// себеп: бұл жолдар ЕШҚАШАН RAM-ға көшірілмейді.
const char DEVICE_ID[] PROGMEM = "APL-TEMPERATURE-01";
const char MODEL[] PROGMEM = "V1";
const char SENSOR_TYPE[] PROGMEM = "TEMPERATURE";
const char CHIP_NAME[] PROGMEM = "DS18B20";
const char FIRMWARE_VERSION[] PROGMEM = "1.0";

// ---- DS18B20 (1-Wire, D2 пині) -------------------------------------------
#define ONE_WIRE_PIN 2
OneWire oneWire(ONE_WIRE_PIN);
DallasTemperature sensors(&oneWire);
DeviceAddress sensorAddress;
bool sensorReady = false;
unsigned long lastSensorRetryMillis = 0;
const unsigned long SENSOR_RETRY_INTERVAL_MS = 2000;

// 12-bit ажыратымдылық — ең жоғары дәлдік (0.0625°C қадам), datasheet
// бойынша ~750 ms conversion уақыты соған сай.
const uint8_t TEMPERATURE_RESOLUTION_BITS = 12;
const unsigned long CONVERSION_WAIT_MS = 750;

// ---- OLED SSD1306 128x64 (I2C address 0x3C) -----------------------------
#define OLED_WIDTH 128
#define OLED_HEIGHT 64
Adafruit_SSD1306 display(OLED_WIDTH, OLED_HEIGHT, &Wire, -1);
bool oledReady = false;

// ---- Non-blocking conversion-wait күйі -----------------------------------
// INA226 firmware-дегі "sample averaging" орнына — бір ғана DS18B20
// conversion циклін delay()-сіз күту.
bool conversionPending = false;
unsigned long conversionStartMillis = 0;
unsigned long lastOledMillis = 0;
const unsigned long OLED_INTERVAL_MS = 250;

// ---- Serial жол буфері (line-based, \n/\r\n) ---------------------------
// Voltage/Current Sensor-мен бірдей — heap allocation-сіз, тұрақты
// өлшемді char[] буфер (§"root cause: Arduino String class").
const size_t LINE_BUFFER_SIZE = 40;
char lineBuffer[LINE_BUFFER_SIZE];
size_t lineLength = 0;

// ---- Ағымдағы тәжірибе ID (SET_EXP арқылы өзгереді) --------------------
// Бос мән — ЕШБІР нақты тәжірибе ID-мен СӘЙКЕС КЕЛМЕЙДІ (Voltage/
// Current Sensor firmware-мен бірдей себеп: docs/serial_protocol.md §6).
// "metal-resistance-temperature" (29 таңба) ЕКІ whitelist id-нің ЕҢ
// ҰЗЫНЫ болғандықтан, буфер соған +қор етіп 32-ге қойылды (Voltage/
// Current Sensor-дегі 24-тен үлкен — сол екі файл да осы тәжірибенің
// ұзын id-ін сыйдыру үшін дәл СОЛ мәнге көтерілді, тарихи параллель
// қашықтан толықтырылды).
const uint8_t EXPERIMENT_ID_MAX_LEN = 32;
char currentExperimentId[EXPERIMENT_ID_MAX_LEN] = "";

// ---- Support етілетін тәжірибе id-лерінің whitelist-і -------------------
// Бұл сенсор ЕКІ тәжірибеге қатысады:
//  - "metal-resistance-temperature" (электр модулі №8, VOLTAGE+CURRENT+
//    TEMPERATURE үш Arduino бірге);
//  - "compare-heat-quantity" (жылу модулі №1, kезeng 39B, ЖАЛҒЫЗ осы
//    Arduino — required_sensor_types=("TEMPERATURE",)).
const char EXPERIMENT_ID_STR_0[] PROGMEM = "metal-resistance-temperature";
const char EXPERIMENT_ID_STR_1[] PROGMEM = "compare-heat-quantity";

const char *const SUPPORTED_EXPERIMENT_IDS[] PROGMEM = {
  EXPERIMENT_ID_STR_0,
  EXPERIMENT_ID_STR_1,
};
const uint8_t SUPPORTED_EXPERIMENT_COUNT =
    sizeof(SUPPORTED_EXPERIMENT_IDS) / sizeof(SUPPORTED_EXPERIMENT_IDS[0]);

bool isSupportedExperiment(const char *id) {
  for (uint8_t i = 0; i < SUPPORTED_EXPERIMENT_COUNT; i++) {
    const char *flashId = (const char *)pgm_read_word(&SUPPORTED_EXPERIMENT_IDS[i]);
    if (strcmp_P(id, flashId) == 0) {
      return true;
    }
  }
  return false;
}

void copyExperimentId(const char *source) {
  size_t i = 0;
  for (; i < EXPERIMENT_ID_MAX_LEN - 1 && source[i] != '\0'; i++) {
    currentExperimentId[i] = source[i];
  }
  currentExperimentId[i] = '\0';
}

// SET_EXP= префиксі — PROGMEM (RAM-ды жемейді).
const char SET_EXP_PREFIX[] PROGMEM = "SET_EXP=";
const size_t SET_EXP_PREFIX_LEN = 8; // strlen("SET_EXP=")

// "HELLO?" салыстыруы (register-тәуелсіз, heap allocation-сіз).
bool isHelloCommand(const char *line) {
  static const char HELLO_CMD[] PROGMEM = "HELLO?";
  for (uint8_t i = 0; i < 6; i++) {
    if (line[i] == '\0') {
      return false;
    }
    char c = line[i];
    if (c >= 'a' && c <= 'z') {
      c = c - 'a' + 'A';
    }
    if (c != (char)pgm_read_byte(&HELLO_CMD[i])) {
      return false;
    }
  }
  return line[6] == '\0'; // дәл 6 таңба (артық жоқ)
}

// Жол басы/соңындағы бос орын/CR/LF-ты ОРНЫНДА (heap allocation-сіз) алып
// тастайды.
void trimInPlace(char *s) {
  size_t start = 0;
  while (s[start] == ' ' || s[start] == '\t' || s[start] == '\r' || s[start] == '\n') {
    start++;
  }
  size_t len = strlen(s + start);
  while (len > 0) {
    char c = s[start + len - 1];
    if (c == ' ' || c == '\t' || c == '\r' || c == '\n') {
      len--;
    } else {
      break;
    }
  }
  if (start > 0) {
    memmove(s, s + start, len);
  }
  s[len] = '\0';
}

void startConversionIfIdle();

void setup() {
  Serial.begin(115200);
  delay(30); // USB-serial чиптің ашылуынан кейін тұрақтандыру
  Wire.begin();

  sensors.begin();
  sensorReady = sensors.getAddress(sensorAddress, 0);
  if (sensorReady) {
    sensors.setResolution(sensorAddress, TEMPERATURE_RESOLUTION_BITS);
    // requestTemperatures() блоктамай (async) қайтуы үшін міндетті —
    // әйтпесе кітапхана өзі ішінде conversion аяқталғанша күтеді.
    sensors.setWaitForConversion(false);
  }
  // DS18B20 табылмаса да (sensorReady=false), Serial протокол істей
  // береді: HELLO?/SET_EXP= жауап береді, тек measurement жіберілмейді.

  oledReady = display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  if (oledReady) {
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(0, 0);
    display.println(F("TEMPERATURA SENSORY"));
    display.display();
  }
  // OLED табылмаса да (oledReady=false), sensor/protocol жұмысына мүлде
  // әсер етпейді.

  unsigned long now = millis();
  lastSensorRetryMillis = now;
}

void loop() {
  readSerialCommands();

  unsigned long now = millis();

  if (!sensorReady && (now - lastSensorRetryMillis >= SENSOR_RETRY_INTERVAL_MS)) {
    // Қосылуы босап қалған/кешірек жалғанған DS18B20-ны қайта тексеру.
    lastSensorRetryMillis = now;
    sensorReady = sensors.getAddress(sensorAddress, 0);
    if (sensorReady) {
      sensors.setResolution(sensorAddress, TEMPERATURE_RESOLUTION_BITS);
      sensors.setWaitForConversion(false);
      conversionPending = false;
    }
  }

  if (sensorReady) {
    startConversionIfIdle();
    if (conversionPending && (now - conversionStartMillis >= CONVERSION_WAIT_MS)) {
      float celsius = sensors.getTempCByIndex(0);
      conversionPending = false;
      finalizeMeasurement(celsius);
    }
  }
}

// ---- Serial командаларды оқу (line-based, delay() жоқ) -----------------
void readSerialCommands() {
  while (Serial.available() > 0) {
    char incomingChar = (char)Serial.read();

    if (incomingChar == '\n' || incomingChar == '\r') {
      if (lineLength == 0) {
        continue; // CRLF-тің екінші таңбасы немесе қайталанған терминатор
      }
      lineBuffer[lineLength] = '\0';
      handleLine(lineBuffer);
      lineLength = 0;
      continue;
    }

    if (lineLength < LINE_BUFFER_SIZE - 1) {
      lineBuffer[lineLength++] = incomingChar;
    } else {
      // Buffer overflow қаупі (тым ұзын/бұзық жол) — Arduino құламайды,
      // жарамсыз жол тасталады, буфер тазаланады.
      lineLength = 0;
    }
  }
}

void handleLine(char *rawLine) {
  trimInPlace(rawLine);

  if (rawLine[0] == '\0') {
    return; // бос жол — елеусіз
  }

  if (isHelloCommand(rawLine)) {
    sendHello(); // sensorReady-ге тәуелсіз — DS18B20 табылмаса да жауап береді
    return;
  }

  if (strncmp_P(rawLine, SET_EXP_PREFIX, SET_EXP_PREFIX_LEN) == 0) {
    const char *requestedId = rawLine + SET_EXP_PREFIX_LEN;
    while (*requestedId == ' ' || *requestedId == '\t') {
      requestedId++; // "=" мен мән арасындағы бос орынды өткізіп жіберу
    }

    if (isSupportedExperiment(requestedId)) {
      copyExperimentId(requestedId);
    }
    // Support ЕТІЛМЕЙТІН/бүлінген id келсе — currentExperimentId
    // ӨЗГЕРМЕЙДІ (ескі мән сақталады).
    Serial.print(F("OK,EXP="));
    Serial.println(currentExperimentId);
    return;
  }

  // Белгісіз команда — Arduino-ны құлатпайды, жай елеусіз қалдырылады.
}

void sendHello() {
  Serial.print(F("TYPE=HELLO,DEV="));
  Serial.print((const __FlashStringHelper *)DEVICE_ID);
  Serial.print(F(",MODEL="));
  Serial.print((const __FlashStringHelper *)MODEL);
  Serial.print(F(",SENSOR="));
  Serial.print((const __FlashStringHelper *)SENSOR_TYPE);
  Serial.print(F(",CHIP="));
  Serial.print((const __FlashStringHelper *)CHIP_NAME);
  Serial.print(F(",FW="));
  Serial.println((const __FlashStringHelper *)FIRMWARE_VERSION);
}

// ---- Non-blocking DS18B20 conversion state machine -----------------------
void startConversionIfIdle() {
  if (conversionPending) {
    return; // алдыңғы conversion әлі аяқталған жоқ
  }
  sensors.requestTemperatures(); // setWaitForConversion(false) — лезде қайтады
  conversionStartMillis = millis();
  conversionPending = true;
}

// ---- Финализация (DS18B20 — зауытта калибрленген, қосымша калибрлеу
// коэффициенті ЖОҚ; тек ажыратылған/қате оқылымды сүзу) --------------------
void finalizeMeasurement(float celsius) {
  // DEVICE_DISCONNECTED_C — DallasTemperature кітапханасының сым
  // ажыратылған/CRC қатесі жағдайындағы sentinel мәні (-127.0). Мұндай
  // өлшем PC-ге жіберілмейді (жалған "-127°C" нүктесі графикті бұзбасын).
  if (celsius == DEVICE_DISCONNECTED_C) {
    DEBUG_PRINTLN("DS18B20 disconnected, skip");
    return;
  }

  DEBUG_PRINT("Temperature(C): ");
  DEBUG_PRINTLN(celsius, 4);

  sendMeasurement(celsius);
  updateDisplay(celsius);
}

void sendMeasurement(float celsius) {
  Serial.print(F("EXP="));
  Serial.print(currentExperimentId);
  Serial.print(F(",TEMP="));
  Serial.println(celsius, 3);
}

void updateDisplay(float celsius) {
  if (!oledReady) {
    return; // OLED жоқ/табылмаған — measurement/protocol-ға әсер етпейді
  }
  unsigned long now = millis();
  if (now - lastOledMillis < OLED_INTERVAL_MS) {
    return;
  }
  lastOledMillis = now;

  display.clearDisplay();
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println(F("TEMPERATURA SENSORY"));

  display.setTextSize(2);
  display.setCursor(0, 24);
  display.print(celsius, 2);
  display.println(F(" C"));
  display.display();
}
