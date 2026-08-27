# Voltage Sensor firmware

`voltage_sensor.ino` — Arduino Nano/Uno + INA226 (I2C) + SSD1306 OLED
үшін Voltage Sensor firmware-і. Хаттама:
[`docs/serial_protocol.md`](../../docs/serial_protocol.md)
(2-4, 11, 12, 13-бөлімдер).

Сым жалғау (wiring), жүктеу және толық end-to-end сынақ қадамдары үшін:
[`docs/hardware_test_guide.md`](../../docs/hardware_test_guide.md).

## Қажетті кітапханалар

- **"INA226_WE" by Wolfgang Ewald** (Rob Tillaart-тың `INA226` кітапханасы
  ЕМЕС — нақты жұмыс істеп тұрған hardware коды `INA226_WE`-нің
  `getBusVoltage_V()`/`init()` API-ымен жазылған).
- **"Adafruit GFX Library"**
- **"Adafruit SSD1306"**

Барлығы Arduino IDE → Tools → Manage Libraries арқылы орнатылады.

## Калибрлеу (нақты hardware-де тексерілген, өзгертпеу керек)

```cpp
const float VOLTAGE_CAL = 1.000;
const float ZERO_THRESHOLD_V = 0.003;
const uint8_t SAMPLE_COUNT = 20;
```

20 sample (5 мс аралықпен, non-blocking) орташаланып, `VOLTAGE_CAL`-ға
көбейтіліп, 0.003 V-тан төмен болса 0-ге теңеледі — PC-ге дәл осы
калибрленген мән жіберіледі (`EXP=<id>,U=<calibrated_voltage>`).

## Debug режимі

`.ino` файлының басындағы `#define DEBUG_SERIAL 0` мәнін `1`-ге
өзгертсеңіз, `Voltage(V): ...` жолы Serial Monitor-ға қосымша шығады.
**Production/PC интеграциясында 0 күйінде қалдырыңыз.**
