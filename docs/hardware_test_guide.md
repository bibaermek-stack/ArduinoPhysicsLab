# Voltage Sensor / Current Sensor — End-to-End Hardware сынақ нұсқаулығы

Бұл нұсқаулық нақты Arduino + INA226 құрылғыларымен (Voltage Sensor
**және** Current Sensor) Arduino Physics Lab қолданбасын толық тізбекте
(end-to-end) сынау үшін арналған.

> **Multi-device аудиттен кейінгі маңызды түзету:** барлық электр
> тәжірибелері (`current-voltage`, `ohms-law`, ...) енді Voltage Sensor
> **және** Current Sensor екеуінің бірге қосылуын талап етеді
> (`required_sensor_types=("VOLTAGE","CURRENT")`) — `current` арнасы
> қайта `required=True`. §4-тегі сынақ жалғыз Voltage Sensor-мен
> **толық валидті Measurement бермейді** (readouts "—" қалады,
> `warning_occurred`-те "current мәні жоқ" секілді хабарлама шығады) —
> бұл **дұрыс мінез-құлық**, ток өлшенбесе қуат/кедергі есептелмеуі
> тиіс. §4 — тек Voltage Sensor firmware/HELLO/SET_EXP/serial
> pipeline-дің оқшау дұрыс жұмыс істейтінін тексеруге арналған. Екі
> сенсормен толық Ohm's Law сынағы үшін §7-ні қараңыз (Current Sensor
> firmware дайын, `firmware/current_sensor/`).

## 1. Қажетті жабдық

- 2× Arduino Nano немесе Uno (немесе толық pin-compatible клон) — біреуі Voltage Sensor, біреуі Current Sensor
- 2× INA226 модулі (I2C breakout board, әдепкі address 0x40)
- 2× USB кабелі (әр Arduino ↔ PC, жеке COM-порт)
- Өлшенетін тізбек: кернеу көзі (0–5V) + жүктеме (Ток Sensor-дың шунты арқылы өтетін)

## 2. Сым жалғау (wiring)

Voltage Sensor (bus voltage параллель өлшенеді):

```
   Arduino #1 (Voltage)        INA226 breakout
   ─────────────────            ───────────────
        5V  ───────────────────  VCC
        GND ───────────────────  GND
        A4 (SDA) ──────────────  SDA
        A5 (SCL) ──────────────  SCL

   Өлшенетін тізбек:
        VIN+ ───────────────────  VBUS (немесе IN+)
        VIN- ───────────────────  GND (немесе IN-, шунт арқылы)
```

Current Sensor (ток тізбек арқылы тізбектей — сериялы — өтуі керек):

```
   Arduino #2 (Current)        INA226 breakout
   ─────────────────            ───────────────
        5V  ───────────────────  VCC
        GND ───────────────────  GND
        A4 (SDA) ──────────────  SDA
        A5 (SCL) ──────────────  SCL

   Өлшенетін тізбек (ток шунт арқылы өтуі керек):
        Тізбек (+) ─────────────  IN+
        IN- ─────────────────────  Жүктемеге
```

- INA226 ADDR pin-дері (A0/A1) қосылмаса — әдепкі I2C мекенжай `0x40`
  (firmware осыны күтеді). Екі Arduino да жеке I2C шинасында
  тұрғандықтан, екеуінің де `0x40` қолдануы қайшылық тудырмайды.
  Дәнекерлеп өзгертсеңіз, тиісті `.ino` файлдағы `INA226 ina226(0x40);`
  жолын сәйкес мекенжайға өзгертіңіз.
- Кернеу көзінің **max 30V**, токтың **max 5A** (INA226 шунтына
  байланысты) шектен аспауын қадағалаңыз (`VOLTAGE_CHANNEL`/
  `CURRENT_CHANNEL` валидация шегі де осыған сай,
  `modules/electricity/experiments_config.py`). Current Sensor-дың
  шунт калибрлеуі (`SHUNT_MAX_CURRENT_A`/`SHUNT_RESISTANCE_OHM`) өз
  платаңызға сай екенін тексеріңіз (`firmware/current_sensor/README.md`).

## 3. Firmware жүктеу

**Voltage Sensor (Arduino #1):**

1. Arduino IDE-де `firmware/voltage_sensor/voltage_sensor.ino` ашыңыз.
2. **Tools → Manage Libraries** → **"INA226_WE" by Wolfgang Ewald**,
   **"Adafruit GFX Library"**, **"Adafruit SSD1306"** кітапханаларын
   орнатыңыз (толығырақ: `firmware/voltage_sensor/README.md`).
3. **Tools → Board** → "Arduino Nano" (немесе "Arduino Uno") таңдаңыз,
   дұрыс COM портты таңдаңыз.
4. **Upload** басыңыз.

**Current Sensor (Arduino #2):**

1. Arduino IDE-де `firmware/current_sensor/current_sensor.ino` ашыңыз.
2. **Tools → Manage Libraries** → **"INA226" by Rob Tillaart** (Voltage
   Sensor-дан БӨЛЕК кітапхана — екеуі әр түрлі INA226 кітапхана
   қолданады), **"Adafruit GFX Library"**, **"Adafruit SSD1306"**
   орнатыңыз (толығырақ: `firmware/current_sensor/README.md`).
3. **Tools → Board/Port** — Current Sensor Arduino-сының COM портын таңдаңыз.
4. **Upload** басыңыз.

Екеуін де жүктегеннен кейін: **Tools → Serial Monitor** ашып, baud
rate-ті **115200**-ге қойып тексеруге болады (сынақтың соңында жабуды
ұмытпаңыз — бір уақытта екі бағдарлама бір COM-портты аша алмайды).

## 3b. Тақтайда міндетті тексеру (OLED / HELLO / 10 Hz)

Firmware-де PROGMEM/`F()` және OLED 4 Hz жаңарту бар, бірақ **нақты
ATmega328P-де** мына үш нүктені Serial Monitor (115200) арқылы өту керек:

| № | Тексеру | Күтілетін нәтиже |
|---|---|---|
| A | Қуат берілгеннен кейін OLED | «KERNEU SENSOR» / «TOK SENSORY» + өлшем. Бос экран = SRAM/I2C; `DEBUG_FREE_RAM 1` қосып `Free RAM after setup()` > ~400 байт екенін қараңыз |
| B | `HELLO?` бірнеше рет | Әр жолы тұрақты `TYPE=HELLO,DEV=APL-…` жауап. INA226 жоқ болса да HELLO жауап береді |
| C | `SET_EXP=ohms-law` сосын 10 с күту | `OK,EXP=ohms-law`, содан кейін ~10 Hz `EXP=ohms-law,U=…` / `I=…`. COM порты үзілмеуі, жолдар кесілмеуі тиіс |

Осы үш қадам өтпесе, PC қосымшасын кінәламаңыз — firmware/тақтайды қайта тексеріңіз.

## 4. Толық сынақ қадамдары

| № | Әрекет | Күтілетін нәтиже |
|---|---|---|
| 1 | Firmware жүктелді, USB қосылды | Arduino жыпылықтайды (power LED), Serial Monitor-да ешбір қате жоқ |
| 2 | INA226 сымдалды | — |
| 3 | USB PC-ге қосылды | ОС жаңа COM портты таниды |
| 4 | Arduino Physics Lab іске қосу | `python main.py` — Home беті ашылады |
| 5 | "Электр құбылыстары" → "Электр тізбегін құрастыру және ток күшін өлшеу" таңдау | ExperimentWorkspacePage ашылады, тақырып "Электр тізбегін құрастыру және ток күшін өлшеу" |
| 6 | DevicePanel-де "Жаңарту" басу | Жаңа COM порт тізімде көрінеді |
| 7 | Портты таңдап, "Анықтау" басу | ~1 секундтан кейін карточка пайда болады: **Кернеу датчигі**, `device_id=APL-VOLTAGE-01`, Chip: INA226 |
| 8 | Карточканы басу (таңдау) | Workspace "құрылғы бар" күйіне ауысады, readouts "—" |
| 9 | "▶ Бастау" басу | Status: "Өлшеу жүріп жатыр"; Serial Monitor-да `SET_EXP=current-voltage` жіберілгенін, `OK,EXP=current-voltage` келгенін көресіз |
| 10 | Кернеу көзін өзгерту | Readout-та **Кернеу "—" күйінде қалады** (Current Sensor қосылмағандықтан) — бұл дұрыс, төмендегі ескертуді қараңыз. Serial Monitor-да `EXP=current-voltage,U=...` жолдары келіп жатқанын көресіз |
| 11 | "■ Тоқтату" басу | Status: "Өлшеу тоқтатылды" |
| 12 | "📤 Экспорт" → CSV | Сессияда Measurement жоқ болғандықтан (тек 1 сенсор), "Экспорттайтын дерек жоқ" көрсетіледі — бұл §7-де (2 сенсор) өзгереді |

## 5. Күтілетін Serial жолдары (диагностика үшін)

Handshake:

```
PC  -> HELLO?
Ard -> TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE,CHIP=INA226,FW=1.0
```

Бастау:

```
PC  -> SET_EXP=current-voltage
Ard -> OK,EXP=current-voltage
```

Үздіксіз өлшеу (10 Hz):

```
Ard -> EXP=current-voltage,U=5.024
Ard -> EXP=current-voltage,U=5.019
Ard -> EXP=current-voltage,U=5.031
...
```

Current Sensor үшін дәл сол хаттама, тек `SENSOR=CURRENT`/`I=`:

```
PC  -> HELLO?
Ard -> TYPE=HELLO,DEV=APL-CURRENT-01,MODEL=V1,SENSOR=CURRENT,CHIP=INA226,FW=1.0

PC  -> SET_EXP=ohms-law
Ard -> OK,EXP=ohms-law

Ard -> EXP=ohms-law,I=0.218
Ard -> EXP=ohms-law,I=0.219
...
```

## 6. Ақаулықтарды жою (troubleshooting)

| Белгі | Ықтимал себеп | Не істеу керек |
|---|---|---|
| "Анықтау" ешқашан карточка бермейді (HELLO timeout) | Baud rate сәйкес емес / firmware жүктелмеген / басқа қолданба (Serial Monitor) портты ұстап тұр | Serial Monitor-ды жабыңыз, baud 115200 екенін тексеріңіз |
| Readout әрдайым "—" | INA226 сымдалмаған/дұрыс емес address | Сымдарды тексеріңіз — INA226 табылмаса (`ina226.init()`/`ina226.begin()` `sensorReady=false` қайтарса), Arduino measurement жібермейді, тек HELLO/SET_EXP жауап береді |
| OLED-те ештеңе көрінбейді | SSD1306 сымдалмаған/дұрыс емес address (0x3C) | `oledReady=false` болса, firmware өзгеріссіз жұмыс істей береді — тек экран өшеді, Serial/measurement/identify тоқтамайды |
| Кернеу мәні тым тұрақсыз/нөл | GND ортақ емес, шунт дұрыс жалғанбаған | Ground байланысын тексеріңіз |
| USB суырылып қалды | — | `DevicePanel`/`MeasurementWorkspace` автоматты "Құрылғымен байланыс үзілді" күйіне өтеді, қолданба құламайды — қайта Identify жасаңыз |
| Бастапқы бірнеше пакет жоғалады | Arduino reset болғаннан кейін handshake/loop толық тұрақтанбаған | Қалыпты жағдай — 10 Hz ағын секундтар ішінде тұрақтанады |

## 7. Multi-device (Ohm's Law, 2 сенсор) толық сынағы

Current Sensor firmware-і (`firmware/current_sensor/current_sensor.ino`)
дайын — бұл §-ті нақты екі Arduino-мен толық орындауға болады (§1-3-те
екеуін де жүктегеннен кейін).

Екі Voltage Sensor + Current Sensor қосылғанда күтілетін UI ағыны:

1. "Электр құбылыстары" → "Тізбек бөлігі үшін кернеудің ток күшіне тәуелділігін зерттеу" таңдалады.
2. DevicePanel-де **"Қажетті сенсорлар"** checklist пайда болады: "○ Кернеу датчигі", "○ Ток датчигі".
3. Voltage Sensor портын (мыс. COM3) таңдап, "Анықтау" — HELLO жауабынан `SENSOR=VOLTAGE` танылады, checklist-те "✓ Кернеу датчигі" болады.
4. Current Sensor портын (мыс. COM4) таңдап, "Анықтау" — checklist-те "✓ Ток датчигі" болады.
5. Екеуі де ✓ болған сәтте ғана "▶ Бастау" батырмасы enabled болады.
6. Бастау басылғанда, **екі портқа да** `SET_EXP=ohms-law` жіберіледі, екеуі де `OK,EXP=ohms-law` қайтарады.
7. COM3-тен `EXP=ohms-law,U=5.024`, COM4-тен `EXP=ohms-law,I=0.218` келеді — 500 мс staleness терезесі ішінде екеуі де келсе, workspace-те **Кернеу=5.024 V, Ток=0.218 A, Кедергі=23.05 Ω** бірден пайда болады.
8. Кез келген порт ажыратылса (мыс. Current Sensor USB суырылса), тәжірибе автоматты тоқтайды, checklist-те сол сенсор "○"-ге қайтады, "Бастау" қайта disabled болады, статуста қай порт ажырағаны көрсетіледі.
9. "■ Тоқтату" басу — Status: "Өлшеу тоқтатылды".
10. "📤 Экспорт" → CSV — файл сақталады, ішінде voltage/current/resistance бағандары бар барлық жиналған жолдар болады.

**Ескерту:** COM нөмірлері тек мысал — Voltage Sensor мен Current
Sensor қай COM-портқа жалғанса да (мыс. Voltage → COM7, Current →
COM5), `MultiSensorExperimentCoordinator` оларды **тек HELLO-дағы
`SENSOR=` мәні бойынша** таниды, порт нөміріне тәуелді емес.
