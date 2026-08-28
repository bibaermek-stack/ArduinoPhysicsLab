/*
  Current Sensor — Arduino Physics Lab firmware
  ================================================

  Құрылғы: APL-CURRENT-01 (SENSOR=CURRENT)
  Board:   Arduino Nano / Uno (ATmega328P, 16 MHz, 5V логика).
           *** BOARD-SPECIFIC ***
           Voltage Sensor firmware-мен бірдей baseline: Nano/Uno-ге
           жазылды (A4=SDA, A5=SCL hardware I2C pin-дері, 5V-ке
           толерантты INA226/OLED).

  Sensor:  INA226 (I2C, address 0x40).
  OLED:    SSD1306 128x64 (I2C, address 0x3C).
  Library: "INA226" by Rob Tillaart, "Adafruit GFX Library",
           "Adafruit SSD1306" (Arduino Library Manager арқылы орнатылады).

  ================================================================
  ВАЛИДТЕЛГЕН КАЛИБРЛЕУ (нақты hardware-де Vernier reference арқылы
  тексерілген, өзгертпеу керек):
  ================================================================
    1. INA226.getCurrent() арқылы SAMPLE_COUNT=20 рет оқу
    2. Әр sample арасында 5 ms
    3. Орташа rawCurrent_A есептеу
    4. rawCurrent_A < 0 болса, абсолют мән алу
    5. rawCurrent_mA = rawCurrent_A * 1000
    6. current_mA = rawCurrent_mA * CURRENT_CAL
    7. current_mA < ZERO_THRESHOLD_mA болса → 0
    8. current_A = current_mA / 1000  ← PC-ге ДӘЛ осы мән жіберіледі

  Ескерту: осы кітапхана нұсқасында setMaxCurrentShunt() жоқ (ескі
  Voltage Sensor firmware-де қолданылған калибрлеу әдісі бұл жерде
  ҚОЛДАНЫЛМАЙДЫ) — барлық калибрлеу CURRENT_CAL көбейткіші арқылы,
  жоғарыдағы 8 қадаммен жасалады.

  ================================================================
  NON-BLOCKING SAMPLING (маңызды дизайн шешімі):
  ================================================================
  Ескі (hardware-де тексерілген) код 20 sample-ды delay(5) арқылы,
  яғни 100 ms бойы Serial-ды блоктап жинайтын. Бұл Arduino Physics Lab
  протоколында жарамсыз — сол 100 ms ішінде PC жіберген HELLO?/SET_EXP=
  командасы оқылмай қалар еді.

  Шешім: delay(5) орнына millis()-негізді кішкентай state machine
  (collectSampleIfDue()) қолданылады — loop() әр айналымда Serial-ды
  бірден оқиды (readSerialCommands()), тек INA226-дан жаңа sample алу
  "соңғы sample-дан 5 ms өтті ме" тексерісімен шектеледі. Осылай
  20 sample × 5 ms = 100 ms жиынтық уақыты САҚТАЛАДЫ (калибрлеу
  семантикасы бірдей — дәл 20 sample, дәл 5 ms аралықпен), бірақ
  Serial ешқашан блокталмайды. Бір averaging циклінің өзі ~100 ms
  (10 Hz) созылатындықтан, бөлек сыртқы "measurement timer" қажет
  болмады — ол дәл осы циклмен дәл сәйкес келеді.

  Протокол: docs/serial_protocol.md (2-4, 11, 12, 13-бөлімдер):

    PC  -> "HELLO?"
    Ard -> "TYPE=HELLO,DEV=APL-CURRENT-01,MODEL=V1,SENSOR=CURRENT,CHIP=INA226,FW=1.0"

    PC  -> "SET_EXP=<experiment-id>"
    Ard -> "OK,EXP=<experiment-id>"

    Ard -> "EXP=<experiment-id>,I=<calibrated_current_A>"     (~10 Hz)

  Ақаулық өңдеу:
  - INA226 табылмаса: measurement жіберілмейді, бірақ HELLO/SET_EXP
    Serial командалары әдеттегідей жұмыс істей береді (while(true)
    секілді толық тоқтату ЖОҚ).
  - OLED табылмаса: экран жаңартылмайды, бірақ sensor/protocol жұмысына
    мүлде әсер етпейді.
  - Debug жолдары (Raw:/Current:) production Serial ағынына араласпайды
    — DEBUG_SERIAL 0-ге тең болғанда толық compile-out болады.

  ================================================================
  SRAM РЕГРЕССИЯСЫНЫҢ АЛДЫН АЛУ (Voltage Sensor firmware-де табылған
  ақаумен бірдей архитектуралық қауіп)
  ================================================================
  Voltage Sensor firmware-де (voltage_sensor.ino) нақты hardware-де
  OLED-тің бос қалу ақауы табылды: ATmega328P-тің 2048 байттық SRAM-ында
  Adafruit_SSD1306 display.begin() ~1024 байттық framebuffer-ді malloc()
  арқылы бөледі, ал `const char[]` түрінде жазылған идентификация/
  whitelist/протокол жолдары (PROGMEM/F() ЖОҚ болғанда) AVR-де бастапқы
  жүктелу кезінде FLASH-тан RAM-ға көшіріледі — бұл RAM қорын тарылтып,
  framebuffer allocation-мен соқтығысады.

  Current Sensor firmware дәл СОЛ АРХИТЕКТУРАны қолданады (whitelist,
  идентификация тұрақтылары, OLED, протокол литералдары) — сондықтан
  әлі нақты hardware-де хабарланбаса да, дәл сол латентті қауіп бар.
  Осы файлда Voltage Sensor-мен БІРДЕЙ түзету алдын ала қолданылды:
  барлық тұрақты жолдар PROGMEM/F(...) арқылы ФЛЕШ-те қалдырылды —
  RAM-ға ЕШҚАШАН көшірілмейді. Есептеу/калибрлеу/heap-free SET_EXP
  parser логикасы МҮЛДЕ өзгермеді, тек жолдардың САҚТАЛУ орны.
*/

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <INA226.h>
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
const char DEVICE_ID[] PROGMEM = "APL-CURRENT-01";
const char MODEL[] PROGMEM = "V1";
const char SENSOR_TYPE[] PROGMEM = "CURRENT";
const char CHIP_NAME[] PROGMEM = "INA226";
const char FIRMWARE_VERSION[] PROGMEM = "1.0";

// ---- Vernier reference-пен калибрленген тұрақтылар (өзгертпеу керек) ---
const float CURRENT_CAL = 0.915;
const float ZERO_THRESHOLD_mA = 0.5;
const uint8_t SAMPLE_COUNT = 20;
const unsigned long SAMPLE_INTERVAL_MS = 5;

// ---- INA226 (I2C address 0x40) -----------------------------------------
INA226 ina226(0x40);
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
unsigned long lastOledMillis = 0;
const unsigned long OLED_INTERVAL_MS = 250; // 4 Hz — I2C OLED 10 Hz Serial-ды бөгемесін

// ---- Serial жол буфері (line-based, \n/\r\n) ---------------------------
const size_t LINE_BUFFER_SIZE = 40;
char lineBuffer[LINE_BUFFER_SIZE];
size_t lineLength = 0;

// ---- Ағымдағы тәжірибе ID (SET_EXP арқылы өзгереді) --------------------
// БОС мән — ЕШБІР нақты тәжірибе ID-мен СӘЙКЕС КЕЛМЕЙДІ (маңызды!). Бұрын
// бұл жерде "ohms-law" хардкодталған еді — сол нақты тәжірибе id-імен
// СӘЙКЕС КЕЛІП ҚАЛУ мүмкіндігі бар "boot default" болатын. Бос мән
// PacketParser бойынша ӘРҚАШАН invalid ("EXP мәні бос",
// docs/serial_protocol.md §6) — сондықтан SET_EXP әлі жетпеген/сәтсіз
// болған кез келген порт өз пакетін ЕШҚАШАН "кездейсоқ" дұрыс деп
// қабылдатпайды.
//
// **Маңызды: Arduino `String` класы емес, ТҰРАҚТЫ өлшемді `char[]` буфері
// қолданылады.** Нақты hardware-де табылған ақау: алдыңғы нұсқада
// `String currentExperimentId` + `handleLine()`-де `String line =
// String(rawLine)` / `line.substring(8)` / `currentExperimentId =
// newExperimentId` — осылардың БӘРІ ATmega328P-тің (тек 2048 байт SRAM)
// heap-інде ӘРБІР SET_EXP командасында ЖАҢА, ӘРТҮРЛІ ұзындықтағы
// allocation жасайтын. Adafruit_SSD1306 (128x64) экраны `begin()`
// шақырылғанда ӨЗІ де тұрақты 1024 байттық буферді malloc() арқылы
// бөліп алады — демек SET_EXP-тің String churn-іне қалатын bos heap
// орны өте аз. Arduino String-тің realloc() сәтсіз болғанда (үлкенірек
// сабай size-ке фрагменттелген heap-те үздіксіз орын табылмаса) ЕШБІР
// қате/құлау шықпайды — String ЖАЙ БОС ("") қалады (құжатталған,
// белгілі AVR/String OOM мінез-құлқы). Бұл дәл байқалған симптомды
// түсіндіреді: қысқа id ("ohms-law", 8 таңба) кіші, оңай табылатын
// фрагментке сыятын да үнемі сәтті болады, ал ұзынырақ id-лер
// ("series-connection" 17, "parallel-connection" 19, "current-work-power"
// 18, "current-voltage" 15 таңба) фрагменттелген heap-те үлкенірек
// үздіксіз блок таппай, silent түрде бос жолға айналады.
//
// Түзету: осы риск класының ТҮБІРІН жою үшін SET_EXP парсингі мен
// currentExperimentId қоймасынан Arduino `String`-тің толық
// АЙНАЛЫМЫ (heap allocation) алынып тасталды — тек тұрақты өлшемді
// `char[]` + `strcmp`/`strncmp` (heap-сіз, стек/статик жад ғана).
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
  delay(30); // USB-serial чиптің ашылуынан кейін тұрақтандыру
  Wire.begin();

  sensorReady = ina226.begin();
  // INA226 табылмаса да (sensorReady=false), Serial протокол істей береді:
  // HELLO?/SET_EXP= жауап береді, тек measurement жіберілмейді.

  oledReady = display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  if (oledReady) {
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(0, 0);
    display.println(F("TOK SENSORY"));
    display.display();
  }
  // OLED табылмаса да (oledReady=false), sensor/protocol жұмысына мүлде
  // әсер етпейді — тек экран жаңартылмайды (while(true) ЖОҚ).

#if DEBUG_FREE_RAM
  // OLED framebuffer malloc()-тен ДӘЛ КЕЙІН — SRAM регрессиясын осы
  // нүктеде байқау ең маңызды (§SRAM РЕГРЕССИЯСЫНЫҢ АЛДЫН АЛУ).
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
    sensorReady = ina226.begin();
    if (sensorReady) {
      // Алдыңғы (ISA226 жоқ кездегі) жартылай жиналған sample-дар
      // жаңа дұрыс оқылымдармен араласпасын.
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

  float rawSample = ina226.getCurrent(); // A (валидтелген reference коды бойынша)
  sampleSum += rawSample;
  sampleIndex++;

  if (sampleIndex >= SAMPLE_COUNT) {
    float rawCurrent_A = sampleSum / (float)SAMPLE_COUNT;
    finalizeMeasurement(rawCurrent_A);
    sampleIndex = 0;
    sampleSum = 0.0;
  }
}

// ---- Калибрлеу (8 қадам, өзгертілмеген) ---------------------------------
void finalizeMeasurement(float rawCurrent_A) {
  if (rawCurrent_A < 0) {
    rawCurrent_A = fabs(rawCurrent_A);
  }

  float rawCurrent_mA = rawCurrent_A * 1000.0;
  float current_mA = rawCurrent_mA * CURRENT_CAL;
  if (current_mA < ZERO_THRESHOLD_mA) {
    current_mA = 0.0;
  }
  float current_A = current_mA / 1000.0;

  DEBUG_PRINT("Raw: ");
  DEBUG_PRINTLN(rawCurrent_A, 4);
  DEBUG_PRINT("Current: ");
  DEBUG_PRINTLN(current_A, 4);

  sendMeasurement(current_A);
  updateDisplay(current_mA);
}

void sendMeasurement(float calibratedCurrentA) {
  Serial.print(F("EXP="));
  Serial.print(currentExperimentId);
  Serial.print(F(",I="));
  Serial.println(calibratedCurrentA, 3);
}

void updateDisplay(float current_mA) {
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
  display.println(F("TOK SENSORY"));

  display.setTextSize(2);
  display.setCursor(0, 24);
  if (current_mA < 1000.0) {
    display.print(current_mA, 1);
    display.println(F(" mA"));
  } else {
    display.print(current_mA / 1000.0, 3);
    display.println(F(" A"));
  }
  display.display();
}
