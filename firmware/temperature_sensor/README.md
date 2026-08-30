# Temperature Sensor firmware

`temperature_sensor.ino` — Arduino Nano/Uno + DS18B20 (1-Wire) + SSD1306
OLED (қосымша) үшін Temperature Sensor firmware-і. Хаттама:
[`docs/serial_protocol.md`](../../docs/serial_protocol.md)
(4, 10, 11, 12, 13-бөлімдер).

**Мәртебесі: нақты hardware-де әлі тексерілмеген.** Voltage/Current
Sensor firmware-і "ВАЛИДТЕЛГЕН КАЛИБРЛЕУ" деп белгіленген — нақты
Vernier reference-пен салыстырылған. Бұл firmware сол дәрежеде **әлі
жоқ**: протокол/SRAM/non-blocking конвенцияларға сай жазылды және
`tests/unit/test_temperature_sensor_firmware_source.py`-мен тексерілді,
бірақ нақты DS18B20 тақтада әлі жүктеліп, өлшенген жоқ. Тексергенге
дейін `modules/electricity/experiments_config.py`-дегі
`METAL_RESISTANCE_TEMPERATURE_EXPERIMENT.is_implemented` мәні
`False` күйінде қалуы керек (§ файлдағы өз түсіндірмесі).

## Сым жалғау (wiring)

```
DS18B20 GND  -> Arduino GND
DS18B20 VDD  -> Arduino 5V
DS18B20 DATA -> Arduino D2  (+ 4.7 kΩ pull-up резисторы DATA-VDD
                арасында — DS18B20 datasheet стандарт талабы, board-та
                жоқ, сыртта қосылады)
OLED SDA/SCL -> Arduino A4/A5 (Voltage/Current Sensor-мен бірдей)
```

## Қажетті кітапханалар

- **"OneWire" by Paul Stoffregen**
- **"DallasTemperature" by Miles Burton**
- **"Adafruit GFX Library"** (тек OLED бар болса)
- **"Adafruit SSD1306"** (тек OLED бар болса)

Барлығы Arduino IDE → Tools → Manage Libraries арқылы орнатылады.

## Калибрлеу — ЖОҚ (әдейі)

DS18B20 — зауытта калибрленген сандық сенсор (±0.5 °C, −10..+85 °C
аралығында, datasheet бойынша). Voltage/Current Sensor-дағы
`VOLTAGE_CAL`/`CURRENT_CAL` секілді сызықтық түзету коэффициенті
**әдейі қосылмады** — ондай тұрақтыны нақты reference термометрсіз
ойдан шығару жалған дәлдік болар еді. Тек жарамсыз/ажыратылған сым
оқылымы (`DEVICE_DISCONNECTED_C` sentinel, −127 °C) сүзіледі.

## Non-blocking conversion (INA226-ден принципті айырмашылық)

INA226 I2C арқылы лезде оқылады, сондықтан Voltage/Current Sensor 20
sample-ды 5 мс аралықпен орташалайды. DS18B20 басқаша: бір
`requestTemperatures()` шақыруының өзі ~750 мс (12-bit) созылады.
Firmware бұл уақытты `delay()`-сіз, `millis()`-негізді state machine
арқылы күтеді (`sensors.setWaitForConversion(false)` +
`conversionPending`/`conversionStartMillis`) — Serial ешқашан
блокталмайды, HELLO?/SET_EXP= кез келген сәтте өңделеді.

## Debug режимі

`.ino` файлының басындағы `#define DEBUG_SERIAL 0` мәнін `1`-ге
өзгертсеңіз, `Temperature(C): ...` жолы Serial Monitor-ға қосымша
шығады. **Production/PC интеграциясында 0 күйінде қалдырыңыз.**

## Тақтада тексеру (жүктегеннен кейін)

1. Arduino IDE Serial Monitor-ды 115200 baud-та ашыңыз (жол соңы:
   Newline немесе Both NL & CR).
2. `HELLO?` жіберіңіз →
   `TYPE=HELLO,DEV=APL-TEMPERATURE-01,MODEL=V1,SENSOR=TEMPERATURE,CHIP=DS18B20,FW=1.0`
   келуі керек.
3. `SET_EXP=metal-resistance-temperature` жіберіңіз →
   `OK,EXP=metal-resistance-temperature`.
4. DS18B20 дұрыс жалғанған болса, шамамен 1 Hz жиілікпен
   `EXP=metal-resistance-temperature,TEMP=<цельсий>` жолдары келе
   бастауы керек (сым/резистор дұрыс емес болса — ешбір `EXP=` жолы
   келмейді, бірақ `HELLO?`/`SET_EXP=` жұмыс істей береді).
5. Бөлмелік температурада (~20-25 °C) мән тұрақты болуы керек; DS18B20
   ұшын қолмен ұстасаңыз, бірнеше секундта мән көтерілуі керек.

## Multi-device (толық тәжірибе, 3 Arduino)

`metal-resistance-temperature` (№8) — Voltage Sensor + Current Sensor +
Temperature Sensor **бір мезгілде, үш бөлек физикалық Arduino** ретінде
қосылуын талап етеді (`MultiSensorExperimentCoordinator`,
[`docs/serial_protocol.md`](../../docs/serial_protocol.md) §13). Үшеуі
де осы тәжірибе id-ін қолдайды —
[`firmware/voltage_sensor/voltage_sensor.ino`](../voltage_sensor/voltage_sensor.ino)
мен
[`firmware/current_sensor/current_sensor.ino`](../current_sensor/current_sensor.ino)-ге
де осы id whitelist-ке қосылды (олар үшеуі бірге тексерілгенге дейін
жаңартылмаған). Толық 3-құрылғылық end-to-end сынақ қадамдары әлі
[`docs/hardware_test_guide.md`](../../docs/hardware_test_guide.md)-ге
қосылған жоқ — қазіргі нұсқа тек Voltage/Current Sensor екі-құрылғылық
сынағын қамтиды.
