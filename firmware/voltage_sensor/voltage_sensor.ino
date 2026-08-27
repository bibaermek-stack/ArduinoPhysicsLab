/*
  Voltage Sensor — Arduino Physics Lab firmware
  ================================================

  Құрылғы: APL-VOLTAGE-01 (SENSOR=VOLTAGE)
  Board:   Arduino Nano / Uno (ATmega328P, 16 MHz, 5V логика).
           *** BOARD-SPECIFIC ***
           Nano/Uno-ге жазылды (A4=SDA, A5=SCL hardware I2C pin-дері,
           5V-ке толерантты INA226/OLED).

  Sensor:  INA226 (I2C, address 0x40).
  OLED:    SSD1306 128x64 (I2C, address 0x3C).
  Library: **"INA226_WE" by Wolfgang Ewald** — Rob Tillaart-тың INA226
           кітапханасына АУЫСТЫРЫЛМАЙДЫ, себебі нақты жұмыс істеп тұрған
           hardware коды дәл осы кітапхананың API-ымен (``getBusVoltage_V()``,
           ``init()``) жазылған. Сонымен қатар "Adafruit GFX Library",
           "Adafruit SSD1306" (Arduino Library Manager арқылы орнатылады).

  ================================================================
  ВАЛИДТЕЛГЕН КАЛИБРЛЕУ (нақты hardware-де тексерілген, өзгертпеу керек):
  ================================================================
    1. ina226.getBusVoltage_V() арқылы SAMPLE_COUNT=20 рет оқу
    2. Әр sample арасында 5 ms
    3. Орташа voltage есептеу
    4. voltage *= VOLTAGE_CAL
    5. voltage < 0.003 V болса → voltage = 0.0
    6. PC-ге дәл осы соңғы calibrated voltage жіберіледі

  Raw (калибрленбеген) voltage ешқашан Serial-ға жіберілмейді.

  ================================================================
  NON-BLOCKING SAMPLING (Current Sensor firmware-мен бірдей паттерн):
  ================================================================
  Ескі (hardware-де тексерілген) код 20 sample-ды delay(5) арқылы,
  яғни 100 ms бойы Serial-ды блоктап жинайтын — бұл Arduino Physics Lab
  протоколында жарамсыз (сол 100 ms ішінде PC жіберген HELLO?/SET_EXP=
  командасы оқылмай қалар еді).

  Шешім: delay(5) орнына millis()-негізді кішкентай state machine
  (collectSampleIfDue()) қолданылады — loop() әр айналымда Serial-ды
  бірден оқиды (readSerialCommands()), тек INA226-дан жаңа sample алу
  "соңғы sample-дан 5 ms өтті ме" тексерісімен шектеледі. 20 sample ×
  5 ms = 100 ms жиынтық уақыты САҚТАЛАДЫ (калибрлеу семантикасы бірдей —
  дәл 20 sample, дәл 5 ms аралықпен), бірақ Serial ешқашан блокталмайды.
  Бір averaging циклінің өзі ~100 ms (10 Hz) созылатындықтан, бөлек
  сыртқы "measurement timer" қажет болмады.

  Протокол: docs/serial_protocol.md (2-4, 11, 12, 13-бөлімдер):

    PC  -> "HELLO?"
    Ard -> "TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE,CHIP=INA226,FW=1.0"

    PC  -> "SET_EXP=<experiment-id>"
    Ard -> "OK,EXP=<experiment-id>"

    Ard -> "EXP=<experiment-id>,U=<calibrated_voltage>"     (~10 Hz)

  Ақаулық өңдеу:
  - INA226 табылмаса: measurement жіберілмейді, бірақ HELLO/SET_EXP
    Serial командалары әдеттегідей жұмыс істей береді (while(true)
    секілді толық тоқтату ЖОҚ) — қолданба құрылғыны әлі де identify
    ете алады.
  - OLED табылмаса: экран жаңартылмайды, бірақ sensor/protocol жұмысына
    мүлде әсер етпейді.
  - Debug жолдары (ескі "Voltage(V)"/"U = ..."/"OLED ERROR"/
    "INA226 not found!") production Serial ағынына араласпайды —
    DEBUG_SERIAL 0-ге тең болғанда толық compile-out болады.

  Multi-device: бұл firmware MultiSensorExperimentCoordinator/
  ChannelAggregator архитектурасымен өзгеріссіз жұмыс істейді (Current
  Sensor-мен бірге Ohm's Law секілді тәжірибелерде) — docs/serial_protocol.md §13.

  ================================================================
  SRAM РЕГРЕССИЯСЫ: OLED бос қалу себебі (нақты hardware-де табылған)
  ================================================================
  Диагностика (пайдаланушы растаған): I2C сканер OLED (0x3C)/INA226
  (0x40) екеуін де көреді, ОҚШАУЛАНҒАН SSD1306 сынағы (basqa ешбір
  global/кітапхана жоқ кезде) сәтті жұмыс істейді — демек wiring/
  address/кітапхана дұрыс. ТОЛЫҚ firmware-де serial/INA226/SET_EXP
  бәрі жұмыс істейді, тек OLED бос қалады. Бұл — ATmega328P-тің 2048
  байттық SRAM-ында КЛАССИКАЛЫҚ "heap/stack collision" симптомы:

    - Adafruit_SSD1306 `display.begin()` ішінде ~1024 байттық
      framebuffer-ді malloc() арқылы бөледі.
    - Бұрын осы файлда барлық хаттама/whitelist/идентификация жолдары
      (мыс. `SUPPORTED_EXPERIMENT_IDS[]`-тегі 5 жол ~82 байт,
      `DEVICE_ID`/`MODEL`/`SENSOR_TYPE`/`CHIP_NAME`/`FIRMWARE_VERSION`
      ~38 байт, протокол фрагменттері) — AVR-де **тек `const` жеткіліксіз**:
      PROGMEM/F() қолданылмаса, бұл деректер бәрібір бастапқы жүктелу
      кезінде FLASH-тан RAM-ға көшіріледі (белгілі Arduino/AVR "const
      әлі де RAM жейді" тұзағы). Бұл ~150-200+ байт .data/.bss-ті
      бекітіп, malloc(1024)-ке қалатын үздіксіз бос орынды/стек қорын
      тарылтады — нәтижесінде framebuffer allocation сәтсіз болады
      немесе кейінгі терең call stack (Serial/float print) heap-пен
      соқтығысады, OLED "үнсіз" бос қалады (қате/құлау ЖОҚ).

  Түзету: барлық тұрақты жолдар (идентификация, whitelist, протокол
  фрагменттері) `PROGMEM`/`F(...)` арқылы ФЛЕШ-те қалдырылды — RAM-ға
  ЕШҚАШАН көшірілмейді. Есептеу/калибрлеу/heap-free SET_EXP parser
  логикасы МҮЛДЕ өзгермеді, тек JOлдардың САҚТАЛУ орны. Қосымша
  `DEBUG_FREE_RAM` (compile-time guard, әдепкі өшірулі) — бос SRAM-ды
  Serial-ға шығарады, келешекте осындай регрессияны ерте байқау үшін.
*/

#include <Wire.h>
#include <INA226_WE.h>
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

// ---- Debug: бос SRAM тексеру (production-да өшірулі — тек SRAM
// регрессиясын диагностикалау үшін 1 етіп қосыңыз) --------------------
// getFreeRamBytes() — heap соңы (__brkval, ешбір malloc әлі болмаса
// __heap_start) мен ағымдағы стек көрсеткіші арасындағы қашықтық —
// AVR Arduino-да кеңінен қолданылатын, кітапханасыз "free RAM" әдісі.
#define DEBUG_FREE_RAM 0

#if DEBUG_FREE_RAM
int getFreeRamBytes() {
  extern int __heap_start, *__brkval;
  int stackVariable;
  return (int)&stackVariable - (__brkval == 0 ? (int)&__heap_start : (int)__brkval);
}
#endif

// ---- Құрылғы идентификациясы (HELLO handshake, өзгермейді) -----------
// PROGMEM — бұл жолдар ЕШҚАШАН RAM-ға көшірілмейді (SRAM түзетуі,
// файл басындағы толық түсіндірмені қараңыз). sendHello()-де
// `(const __FlashStringHelper *)X` арқылы тікелей флештен оқылады.
const char DEVICE_ID[] PROGMEM = "APL-VOLTAGE-01";
const char MODEL[] PROGMEM = "V1";
const char SENSOR_TYPE[] PROGMEM = "VOLTAGE";
const char CHIP_NAME[] PROGMEM = "INA226";
const char FIRMWARE_VERSION[] PROGMEM = "1.0";

// ---- Нақты hardware-де тексерілген калибрлеу тұрақтысы (өзгертпеу керек)
const float VOLTAGE_CAL = 1.000;
const float ZERO_THRESHOLD_V = 0.003;
const uint8_t SAMPLE_COUNT = 20;
const unsigned long SAMPLE_INTERVAL_MS = 5;

// ---- INA226 (I2C address 0x40), INA226_WE кітапханасы -------------------
INA226_WE ina226 = INA226_WE(0x40);
bool sensorReady = false;
unsigned long lastSensorRetryMillis = 0;
const unsigned long SENSOR_RETRY_INTERVAL_MS = 2000;

// ---- OLED SSD1306 128x64 (I2C address 0x3C) -----------------------------
#define OLED_WIDTH 128
#define OLED_HEIGHT 64
Adafruit_SSD1306 display(OLED_WIDTH, OLED_HEIGHT, &Wire, -1);
bool oledReady = false;

// ---- Non-blocking 20-sample averaging күйі ------------------------------
uint8_t sampleIndex = 0;
float sampleSum = 0.0;
unsigned long lastSampleMillis = 0;

// ---- Serial жол буфері (line-based, \n/\r\n) ---------------------------
// SRAM түзетуі: 64→40 байтқа қысқартылды — ең ұзын нақты қолданылатын
// команда "SET_EXP=parallel-connection" (27 таңба + '\0' = 28 байт),
// 40 байт осыған жеткілікті қор (+12 байт) қалдырады, хаттама
// қауіпсіз сыяды (§"shrink buffers only if protocol still safely fits").
const size_t LINE_BUFFER_SIZE = 40;
char lineBuffer[LINE_BUFFER_SIZE];
size_t lineLength = 0;

// ---- Ағымдағы тәжірибе ID (SET_EXP арқылы өзгереді) --------------------
// БОС мән — ЕШБІР нақты тәжірибе ID-мен СӘЙКЕС КЕЛМЕЙДІ (маңызды!). Бос
// мән PacketParser бойынша ӘРҚАШАН invalid ("EXP мәні бос",
// docs/serial_protocol.md §6), сондықтан SET_EXP әлі жетпеген порт
// ешқашан кездейсоқ "дұрыс" болып қабылданбайды.
//
// **Маңызды: Arduino `String` класы емес, ТҰРАҚТЫ өлшемді `char[]` буфері
// қолданылады** — Current Sensor firmware-де нақты hardware-де табылған
// root cause-пен бірдей себеппен (толық түсіндірме сол файлда):
// `String`-тің SET_EXP-те ӘРБІР командада жасайтын heap allocation-дары
// (`String(rawLine)`, `.substring(8)`, `currentExperimentId = ...`)
// Adafruit_SSD1306-ның тұрақты 1024 байттық malloc()-і бар 2048 байттық
// SRAM-да фрагменттеліп, ҰЗЫНЫРАҚ id-лер ("series-connection" т.б.)
// үшін realloc() сәтсіз болғанда String silent түрде БОС қалады —
// қысқа "ohms-law" ғана үнемі сәтті шығатыны осымен түсіндіріледі. Түзету
// — толық heap-сіз `char[]`+`strcmp` парсинг (Voltage/Current екі
// firmware-де де ДӘЛ БІРДЕЙ логика, parity талабы бойынша).
const uint8_t EXPERIMENT_ID_MAX_LEN = 24; // "parallel-connection" (19 таңба) + '\0' + қор
char currentExperimentId[EXPERIMENT_ID_MAX_LEN] = "";

// ---- Support етілетін тәжірибе id-лерінің whitelist-і -------------------
// experiments_config.py-дегі is_implemented=True 5 электр тәжірибесімен
// ДӘЛ сәйкес келеді (жаңа/жоспарлы тәжірибелер ЕШҚАШАН ойдан қосылмайды).
//
// PROGMEM string table (SRAM түзетуі): бұрын бұл 5 жол (~82 байт) +
// pointer массиві (~10 байт) ТОЛЫҒЫМЕН RAM-да сақталатын — қазір екеуі
// де ФЛЕШ-те. isSupportedExperiment() әр pointer-ды pgm_read_word()
// арқылы оқып, strcmp_P() арқылы салыстырады.
const char EXPERIMENT_ID_STR_0[] PROGMEM = "current-voltage";
const char EXPERIMENT_ID_STR_1[] PROGMEM = "series-connection";
const char EXPERIMENT_ID_STR_2[] PROGMEM = "parallel-connection";
const char EXPERIMENT_ID_STR_3[] PROGMEM = "current-work-power";
const char EXPERIMENT_ID_STR_4[] PROGMEM = "ohms-law";

const char *const SUPPORTED_EXPERIMENT_IDS[] PROGMEM = {
  EXPERIMENT_ID_STR_0,
  EXPERIMENT_ID_STR_1,
  EXPERIMENT_ID_STR_2,
  EXPERIMENT_ID_STR_3,
  EXPERIMENT_ID_STR_4,
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

// SET_EXP= префиксі — PROGMEM (RAM-ды жемейді), handleLine()-де
// strncmp_P() арқылы салыстырылады.
const char SET_EXP_PREFIX[] PROGMEM = "SET_EXP=";
const size_t SET_EXP_PREFIX_LEN = 8; // strlen("SET_EXP=")

// "HELLO?" салыстыруы (register-тәуелсіз, heap allocation-сіз, HELLO_CMD
// PROGMEM-де — RAM-ды жемейді).
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
// тастайды — ескі `String::trim()`-мен бірдей семантика.
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

void setup() {
  Serial.begin(115200);
  Wire.begin();

  sensorReady = ina226.init();
  // INA226 табылмаса да (sensorReady=false), Serial протокол істей береді:
  // HELLO?/SET_EXP= жауап береді, тек measurement жіберілмейді.

  oledReady = display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  if (oledReady) {
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(0, 0);
    display.println(F("KERNEU SENSOR"));
    display.display();
  }
  // OLED табылмаса да (oledReady=false), sensor/protocol жұмысына мүлде
  // әсер етпейді — тек экран жаңартылмайды (while(true) ЖОҚ).

#if DEBUG_FREE_RAM
  // OLED framebuffer malloc()-тен ДӘЛ КЕЙІН — SRAM регрессиясын осы
  // нүктеде байқау ең маңызды (§SRAM РЕГРЕССИЯСЫ).
  Serial.print(F("Free RAM after setup(): "));
  Serial.print(getFreeRamBytes());
  Serial.println(F(" bytes"));
#endif

  unsigned long now = millis();
  lastSampleMillis = now;
  lastSensorRetryMillis = now;
}

void loop() {
  readSerialCommands();

  unsigned long now = millis();

  if (!sensorReady && (now - lastSensorRetryMillis >= SENSOR_RETRY_INTERVAL_MS)) {
    // Қосылуы босап қалған/кешірек жалғанған INA226-ны қайта тексеру.
    lastSensorRetryMillis = now;
    sensorReady = ina226.init();
    if (sensorReady) {
      // Алдыңғы (INA226 жоқ кездегі) жартылай жиналған sample-дар жаңа
      // дұрыс оқылымдармен араласпасын.
      sampleIndex = 0;
      sampleSum = 0.0;
    }
  }

  if (sensorReady) {
    collectSampleIfDue(now);
  }
}

// ---- Serial командаларды оқу (line-based, delay() жоқ) -----------------
// '\n' НЕМЕСЕ '\r' екеуі де жол-соңы ретінде қабылданады (Arduino Serial
// Monitor-дың "Newline"/"Carriage return"/"Both NL & CR" режимдерінің
// БАРЛЫҒЫН қолдау үшін) — CRLF жағдайында екінші таңба (lineLength==0
// кезде келетін) елеусіз қалдырылады, қосарланған handleLine() шақыруын
// болдырмайды. ("No line ending" режимі — терминатор ЕШҚАШАН
// жіберілмейтіндіктен — принципті түрде қолдау мүмкін емес, бұл
// шектеу нақты aталған, жасырылмаған.) Нақты қолданба (serial_worker.py)
// әрқашан "\n"-мен аяқтап жібереді — бұл өзгеріс оның жұмысына әсер
// етпейді, тек қолмен Serial Monitor тестілеуге қосымша икемділік береді.
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

// rawLine — lineBuffer-ге тікелей сілтеме (heap allocation-сіз, ОРНЫНДА
// trim жасалады); handleLine() қайтқаннан кейін lineLength=0-ге ысырылады,
// сондықтан мазмұнын сақтап қалу қажет емес.
void handleLine(char *rawLine) {
  trimInPlace(rawLine);

  if (rawLine[0] == '\0') {
    return; // бос жол — елеусіз
  }

  if (isHelloCommand(rawLine)) {
    sendHello(); // sensorReady-ге тәуелсіз — INA226 табылмаса да жауап береді
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
    // ӨЗГЕРМЕЙДІ (ескі мән сақталады). ЕШҚАШАН "OK,EXP=" бос жолмен
    // (сәтті сияқты) ACK жасалмайды — тек whitelist-тегі 5 id ғана
    // қабылданады.
    Serial.print(F("OK,EXP="));
    Serial.println(currentExperimentId);
    return;
  }

  // Белгісіз команда — Arduino-ны құлатпайды, жай елеусіз қалдырылады.
}

void sendHello() {
  // DEVICE_ID/MODEL/SENSOR_TYPE/CHIP_NAME/FIRMWARE_VERSION PROGMEM-де —
  // (const __FlashStringHelper *) арқылы Serial.print/println флештен
  // ТІКЕЛЕЙ оқиды, RAM-ге көшірусіз.
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

// ---- 20 sample × 5 ms non-blocking averaging ----------------------------
void collectSampleIfDue(unsigned long now) {
  if (now - lastSampleMillis < SAMPLE_INTERVAL_MS) {
    return;
  }
  lastSampleMillis = now;

  float rawSample = ina226.getBusVoltage_V(); // V
  sampleSum += rawSample;
  sampleIndex++;

  if (sampleIndex >= SAMPLE_COUNT) {
    float rawVoltage = sampleSum / (float)SAMPLE_COUNT;
    finalizeMeasurement(rawVoltage);
    sampleIndex = 0;
    sampleSum = 0.0;
  }
}

// ---- Калибрлеу (валидтелген, өзгертілмеген) -----------------------------
void finalizeMeasurement(float rawVoltage) {
  float voltage = rawVoltage * VOLTAGE_CAL;
  if (voltage < ZERO_THRESHOLD_V) {
    voltage = 0.0;
  }

  DEBUG_PRINT("Voltage(V): ");
  DEBUG_PRINTLN(voltage, 4);

  sendMeasurement(voltage);
  updateDisplay(voltage);
}

void sendMeasurement(float calibratedVoltage) {
  Serial.print(F("EXP="));
  Serial.print(currentExperimentId);
  Serial.print(F(",U="));
  Serial.println(calibratedVoltage, 3);
}

void updateDisplay(float voltage) {
  if (!oledReady) {
    return; // OLED жоқ/табылмаған — measurement/protocol-ға әсер етпейді
  }

  display.clearDisplay();
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println(F("KERNEU SENSOR"));

  display.setTextSize(2);
  display.setCursor(0, 24);
  display.print(voltage, 3);
  display.println(F(" V"));
  display.display();
}
