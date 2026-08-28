# Current Sensor firmware

`current_sensor.ino` — Voltage Sensor firmware-мен бірдей архитектурадағы,
жеке Arduino/COM-порт арқылы жұмыс істейтін ток датчигі. Хаттама:
[`docs/serial_protocol.md`](../../docs/serial_protocol.md) (2-4, 11,
12, 13-бөлімдер), толық end-to-end сынақ қадамдары:
[`docs/hardware_test_guide.md`](../../docs/hardware_test_guide.md).

## 1. Аппараттық құрал (hardware)

| Компонент | Модель |
|---|---|
| Board | Arduino Nano немесе Uno (ATmega328P, 5V логика) — Voltage Sensor-мен бірдей baseline |
| Ток датчигі (chip) | **INA226** (I2C, address `0x40`) |
| Экран | **SSD1306 OLED, 128×64** (I2C, address `0x3C`) |
| Байланыс | USB Serial (CH340/FTDI — Arduino платасына байланысты) |

INA226 — bus voltage/shunt voltage/current/power монитор чипі; Current
Sensor платасында ол шунт кедергісі арқылы өтетін токты (shunt
voltage-тен) есептеп, `getCurrent()` арқылы қайтарады. Voltage Sensor
да дәл осы чипті қолданады (тек bus voltage оқиды) — екеуі де жеке
физикалық Arduino/I2C шинасында тұрғандықтан, екеуінің де `0x40`
мекенжайын қолдануы қайшылық тудырмайды.

**Калибрлеу:** осы firmware-дегі есептеу логикасы дайын, Vernier
reference құрылғысымен нақты hardware-де тексерілген (валидтелген)
алгоритм — 8-бөлімді қараңыз. Қолданылған INA226 кітапхана нұсқасында
`setMaxCurrentShunt()` әдісі жоқ, сондықтан ішкі калибрлеу
қолданылмайды — барлық түзету бағдарламалық `CURRENT_CAL`
көбейткіші арқылы жасалады.

## 2. Сым жалғау (wiring) және pin mapping

```
   Arduino Nano/Uno            INA226 breakout
   ─────────────────            ───────────────
        5V  ───────────────────  VCC
        GND ───────────────────  GND
        A4 (SDA) ──────────────  SDA
        A5 (SCL) ──────────────  SCL

   Өлшенетін тізбек (ток шунт арқылы өтуі керек):
        Тізбек (+) ─────────────  IN+
        IN- ─────────────────────  Жүктемеге (өлшенетін тұтынушыға)

   Arduino Nano/Uno            SSD1306 OLED (128x64)
   ─────────────────            ───────────────────
        5V (немесе 3.3V) ──────  VCC (модульге сай)
        GND ───────────────────  GND
        A4 (SDA) ──────────────  SDA  (INA226-мен ортақ I2C шина)
        A5 (SCL) ──────────────  SCL  (INA226-мен ортақ I2C шина)
```

- INA226 мен OLED **бір I2C шинасында** (A4/A5), әр түрлі мекенжайда
  (`0x40` / `0x3C`) тұрады — қайшылық жоқ.
- ADDR pin-дер (A0/A1) қосылмаса — INA226 әдепкі I2C мекенжайы `0x40`
  (firmware осыны күтеді). Дәнекерлеп өзгертсеңіз, `.ino` файлындағы
  `INA226 ina226(0x40);` жолын сәйкес мекенжайға өзгертіңіз.
- Ток **max 5A** (`CURRENT_CHANNEL` валидация шегі,
  `modules/electricity/experiments_config.py`) шегінен аспауы тиіс.

## 3. Қажетті Arduino library

1. **"INA226" by Rob Tillaart** (Voltage Sensor firmware-мен бірдей):
   Arduino IDE → **Tools → Manage Libraries** → `INA226` іздеп →
   **"INA226 by Rob Tillaart"** орнатыңыз.
   https://github.com/RobTillaart/INA226
2. **"Adafruit GFX Library"** — Library Manager-де `Adafruit GFX` іздеп орнатыңыз.
3. **"Adafruit SSD1306"** — Library Manager-де `Adafruit SSD1306` іздеп орнатыңыз
   (орнату кезінде "Adafruit BusIO" тәуелділігін де қосу ұсынылады — automatically ұсынылады).

## 3b. Тақтайда тексеру

PROGMEM/`F()` және OLED 4 Hz жаңарту SRAM үшін. Нақты тақтайда OLED,
`HELLO?`, `SET_EXP=`, 10 Hz ағынды
[`docs/hardware_test_guide.md`](../../docs/hardware_test_guide.md) §3b бойынша өтіңіз.

## 4. Serial баптаулары

- **Baud rate:** 115200
- Жол соңы: `\n` немесе `\r\n` (екеуі де қолдау көрсетіледі)

## 5. HELLO protocol

```
PC:      HELLO?
Arduino: TYPE=HELLO,DEV=APL-CURRENT-01,MODEL=V1,SENSOR=CURRENT,CHIP=INA226,FW=1.0
```

`SENSOR=CURRENT` арқылы `MultiSensorExperimentCoordinator`/
`DeviceIdentifier` бұл құрылғыны COM-порт атауына қарамай автоматты
таниды (docs/serial_protocol.md §11).

## 6. SET_EXP protocol

```
PC:      SET_EXP=ohms-law
Arduino: OK,EXP=ohms-law
```

Тәжірибе ауысқанда PC жаңа ID жібереді, Arduino растап, содан кейінгі
measurement пакеттерінде сол ID-ды қолданады (docs/serial_protocol.md §12).

## 7. Measurement packet

```
Arduino: EXP=ohms-law,I=0.218
```

- Кілт: `I` (PacketParser._KEY_MAP: `"I"` → `"current"`)
- Бірлігі: **A (ampere)**, 3 ондық таңба — **калибрленген** мән (8-бөлімді қараңыз), INA226-дың raw мәні ешқашан тікелей жіберілмейді
- Жиілігі: ~10 Hz (20 sample × 5 ms non-blocking averaging циклі, delay() жоқ)

## 8. Калибрлеу (Vernier reference-пен тексерілген, өзгертпеу керек)

```cpp
const float CURRENT_CAL = 0.915;
const float ZERO_THRESHOLD_mA = 0.5;
const uint8_t SAMPLE_COUNT = 20;
```

Алгоритм (`finalizeMeasurement()`):

1. `ina226.getCurrent()` арқылы 20 sample оқылады (әрқайсысы 5 мс аралықпен, non-blocking)
2. Орташа `rawCurrent_A` есептеледі
3. Теріс болса, абсолют мән алынады
4. `rawCurrent_mA = rawCurrent_A × 1000`
5. `current_mA = rawCurrent_mA × CURRENT_CAL`
6. `current_mA < 0.5` болса → `0`
7. `current_A = current_mA / 1000` — PC-ге дәл осы мән жіберіледі

## 9. Debug режимі (production-да өшірулі)

`.ino` файлының басындағы `#define DEBUG_SERIAL 0` мәнін `1`-ге
өзгертсеңіз, `Raw:`/`Current:` жолдары Serial Monitor-ға қосымша
шығады. **Production/PC интеграциясында 0 күйінде қалдырыңыз** — олай
болмаса, бұл жолдар `PacketParser`-ге бөгде мәтін ретінде жетіп,
парсинг қатесі тудыруы мүмкін.

## 10. Arduino IDE-де жүктеу қадамдары

1. `firmware/current_sensor/current_sensor.ino` ашыңыз.
2. **Tools → Manage Libraries** → "INA226 by Rob Tillaart", "Adafruit GFX Library", "Adafruit SSD1306" орнатыңыз (§3).
3. **Tools → Board** → "Arduino Nano" немесе "Arduino Uno" таңдаңыз.
4. Дұрыс COM портты таңдаңыз.
5. **Upload** басыңыз.
6. Тексеру үшін Serial Monitor-ды **115200** baud-пен ашыңыз, содан
   кейін жабуды ұмытпаңыз (бір уақытта екі бағдарлама бір COM-портты
   аша алмайды).

## 11. Voltage Sensor-мен бірге қолдану

Бір тәжірибеде (мыс. "Тізбек бөлігі үшін кернеудің ток күшіне
тәуелділігін зерттеу") Voltage Sensor мен Current Sensor екі
бөлек COM-портта бір мезгілде қосылады. `MultiSensorExperimentCoordinator`
екеуінің де партиалды пакеттерін (`U=`/`I=`) `ChannelAggregator` арқылы
бір толық Measurement-ке біріктіреді — толығырақ
[`docs/serial_protocol.md`](../../docs/serial_protocol.md) §13-те.
