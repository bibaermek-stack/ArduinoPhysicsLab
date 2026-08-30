# Arduino ↔ PC Serial хаттамасы (V1.0)

## 1. Мақсаты

Бұл құжат Arduino негізіндегі зертханалық стенд пен Arduino Physics Lab
қолданбасы арасындағы USB Serial (COM-порт) арқылы деректер алмасу
форматын сипаттайды. Хаттама
[`infrastructure/serial_comm/packet_parser.py`](../infrastructure/serial_comm/packet_parser.py)
модуліндегі `PacketParser` класында іске асырылады.

## 2. Пакет форматы

V1.0-де жеңіл мәтіндік (текстілік) формат қолданылады. Әр пакет —
үтірмен бөлінген `key=value` жұптарынан тұратын бір жол:

```
EXP=E02,U=5.024,I=0.218,T=12.45
```

- Кілттердің реті **міндетті емес** — төмендегі екі пакет те баламалы:

  ```
  EXP=E02,U=4.820,I=0.241,T=12.5
  I=0.241,EXP=E02,T=12.5,U=4.820
  ```

- Кілт пен мән арасында бос орын болмауы тиіс (`U=5.0`, `U = 5.0` емес),
  бірақ үтірден кейінгі бос орындар рұқсат етіледі (`PacketParser` әр
  өрісті автоматты түрде `strip()` етеді).

## 3. Жол соңы (newline) талабы

- Әр пакет бір мәтіндік жол түрінде жіберіледі және `\n` (Arduino
  `Serial.println()` көбіне `\r\n` жібереді) таңбасымен аяқталуы тиіс.
- `PacketParser.parse_line()` жолдың басы мен соңындағы барлық бос
  орындарды (соның ішінде `\r`, `\n`) алып тастайды, сондықтан `\n`
  және `\r\n` арасындағы айырмашылық парсингке әсер етпейді.
- `packet_parser` бір толық жолды ғана өңдейді; жол әлі аяқталмаса,
  пакет `SerialWorker` буферінде келесі `readyRead` оқиғасына дейін
  күтеді (буферлеу логикасы `infrastructure/serial_comm/serial_worker.py`
  ішінде болады, бұл файлдың жауапкершілігі емес).

## 4. Кілттер кестесі

| Serial кілті | `values` ішіндегі ішкі атауы | Бірлігі | Міндетті ме | Сипаттамасы |
|---|---|---|---|---|
| `EXP` | — (`experiment_id` өрісіне жазылады, `values`-те жоқ) | — | Иә | Тәжірибе идентификаторы (мыс., `E02`) |
| `U` | `voltage` | В (Вольт) | Жоқ | Кернеу |
| `I` | `current` | А (Ампер) | Жоқ | Ток күші |
| `T` | `time` | с (секунд) | Жоқ | Тәжірибе басталғаннан өткен уақыт |
| кез келген басқа кілт | кіші әріппен сол қалпында (мыс., `TEMP` → `temp`) | модульге тәуелді | Жоқ | Белгісіз кілт — `warning`-пен бірге `values`-ке сақталады (4-модульдер тарауын қараңыз) |

## 5. Дұрыс пакет мысалдары

```
EXP=E01,U=5.000,I=0.120
EXP=E02,U=4.820,I=0.241,T=12.5
EXP=E05,U=5.100,I=0.200,T=30.0
I=0.241,EXP=E02,T=12.5,U=4.820
EXP=E01,TEMP=24.5
```

Соңғы пакет (`TEMP=24.5`) `is_valid=True` болып қайтады, бірақ
`TEMP` хаттамада ресми анықталмағандықтан `warnings`-ке жазба қосылады
және `values["temp"] = 24.5` ретінде сақталады.

## 6. Қате пакет мысалдары

| Пакет | `is_valid` | Себебі |
|---|---|---|
| `` (бос жол) | `False` | Бос жол |
| `U=5.0,I=0.2` | `False` | `EXP` кілті жоқ |
| `EXP=,U=5.0` | `False` | `EXP` мәні бос |
| `EXP=E02,U=abc` | `False` | `U` сан емес |
| `EXP=E02,U=5,U=6` | `False` | `U` кілті қайталанды |
| `EXP=E02,U=nan` | `False` | `U` ақырлы (finite) сан емес |
| `EXP=E02,I=inf` | `False` | `I` ақырлы (finite) сан емес |
| `EXP=E02,BAD=text` | `False` | `BAD` белгісіз кілт әрі мәні сан емес |

## 7. Arduino жағы: `Serial.println()` арқылы жіберу мысалы

```cpp
void loop() {
  float voltage = readVoltage();
  float current = readCurrent();
  float elapsedTime = millis() / 1000.0;

  Serial.print("EXP=E02,U=");
  Serial.print(voltage, 3);
  Serial.print(",I=");
  Serial.print(current, 3);
  Serial.print(",T=");
  Serial.println(elapsedTime, 2);

  delay(200);
}
```

`Serial.println()` жолдың соңына автоматты түрде newline қосады,
сондықтан 3-бөлімдегі талап орындалады.

## 8. Python жағы: PacketParser қабылдау ағыны

```
QSerialPort.readyRead (SerialWorker, worker thread)
        │  байт буферге жиналады
        ▼
Толық жол (\n дейін) жиналды
        │
        ▼
PacketParser.parse_line(line) → PacketParseResult
        │
        ├─ is_valid == True  → measurement_ready/data_received сигналы
        │                       арқылы ExperimentController-ге беріледі
        │                       (одан әрі DataValidator/CalculationEngine)
        │
        └─ is_valid == False → errors/warnings логке жазылады, пакет
                                тасталады, келесі жолды күтеді
```

`PacketParser` — таза, тек мәтінмен жұмыс істейтін domain-жақын
компонент; ол `QSerialPort`-пен де, UI-мен де тікелей байланыспайды.

## 9. Checksum (`CHK`, міндетті емес)

V1.0 пакетінде `CHK` **міндетті емес** — ескі firmware (`CHK` жоқ)
бұрынғыдай қабылданады.

Егер `CHK` болса, ол XOR checksum: `CHK` өрісінсіз қалған
`key=value` өрістерін үтірмен біріктірген payload-тың UTF-8 байттары
XOR-ланады, нәтиже екітаңбалы үлкен әріпті hex (мыс. `A3`).

```
EXP=E02,U=5.0,I=0.2,CHK=A3
```

- `CHK` сәйкес келмесе немесе hex болмаса — `is_valid=False`, пакет
  өлшем ретінде жазылмайды (USB шуындағы бұзылған жол).
- `CHK` `values` сөздігіне кірмейді (`EXP` сияқты).

## 10. Болашақ модульдер (Жылу, Магниттік, Жарық) жаңа кілттер қосуы

`PacketParser` кез келген белгісіз кілтті automatически (сан болса)
`values`-ке кіші әріппен сақтайды (4-бөлімді қараңыз), сондықтан:

- Жаңа модульдің Arduino эскизі жаңа кілттерді (мыс., `TEMP=` — Жылу,
  `B=` — Магниттік, `LUX=` — Жарық) жай ғана жібере бастаса,
  `packet_parser.py`-ге тиіспей-ақ қабылданады (тек `warning`
  ретінде белгіленеді).
- Егер жаңа кілт нақты модуль үшін **міндетті/ресми** арнаға айналуы
  керек болса (мыс., `TEMP` әрқашан "temperature" ретінде танылуы
  тиіс болса), `PacketParser._KEY_MAP`-қа бір жол қосу жеткілікті
  (`"TEMP": "temperature"`) — қалған парсинг логикасы өзгермейді.
- Бұл кеңейту тек осы файлда ([packet_parser.py](../infrastructure/serial_comm/packet_parser.py))
  жүзеге асады, `domain/`, `ui/` қабаттарына тиіспейді.

**Жаңарту (kезeng 39B):** `TEMP=` жоғарыдағы мысал емес, ЕНДІ нақты
firmware-і бар ([`firmware/temperature_sensor/`](../firmware/temperature_sensor/))
— бірақ "Жылу" модулі үшін емес, электр модулінің №8 тәжірибесі
(`metal-resistance-temperature`) үшін. Firmware нақты hardware-де әлі
тексерілмегендіктен, `is_implemented=False` қалпында.

## 11. HELLO handshake (құрылғыны автоматты тану)

Бағдарлама әр жеке Arduino-негізіндегі датчикті **COM-порт атауына емес**,
құрылғының өзі жіберетін HELLO пакетіне қарап анықтайды. Handshake
[`infrastructure/serial_comm/hello_packet_parser.py`](../infrastructure/serial_comm/hello_packet_parser.py)
(`HelloPacketParser`) және
[`infrastructure/serial_comm/device_identifier.py`](../infrastructure/serial_comm/device_identifier.py)
(`DeviceIdentifier`) арқылы іске асырылады — бұл measurement пакеттерін
(`EXP=...`) өңдейтін `PacketParser`-ден мүлдем бөлек, тәуелсіз хаттама.

**PC жібереді:**

```
HELLO?
```

**Arduino жауап береді** (мысалы, Voltage Sensor):

```
TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE,CHIP=INA226,FW=1.0
```

**Содан кейін өлшеу пакеттерін жібере бастайды:**

```
EXP=E01,U=5.024
```

Басқа датчик түрлері (әрқайсысы — жеке Arduino):

```
TYPE=HELLO,DEV=APL-CURRENT-01,MODEL=V1,SENSOR=CURRENT,CHIP=INA226,FW=1.0
TYPE=HELLO,DEV=APL-ENERGY-01,MODEL=V1,SENSOR=ENERGY,CHIP=INA226,FW=1.0
TYPE=HELLO,DEV=APL-OHMMETER-01,MODEL=V1,SENSOR=OHMMETER,FW=1.0
```

Ohmmeter мысалында `CHIP` кілті қосымша болғандықтан жіберілмеген —
HELLO пакетінде міндетті кілттер: `TYPE`, `DEV`, `MODEL`, `SENSOR`, `FW`.

## 12. `SET_EXP` — эксперимент идентификаторын Arduino-ға жеткізу

**Мәселе:** бір физикалық құрылғы (мыс., Voltage Sensor) бірнеше
`ExperimentDefinition`-де қолданылуы мүмкін (`current-voltage`,
`ohms-law`, `series-connection`, `parallel-connection`,
`current-work-power`) — барлығы дәл сол voltage мәнін оқиды, тек
`EXP` идентификаторы мен есептелетін туынды шамалар бойынша
ажыратылады. Arduino өзі қай тәжірибе таңдалғанын білмейді, сондықтан
PC оны Arduino-ға хабарлауы керек.

**Шешім (A нұсқасы):** `ExperimentController.start_experiment()`
шақырылғанда, PC Arduino-ға ағымдағы `ExperimentDefinition.id`-ды
жібереді:

```
PC:      SET_EXP=ohms-law
Arduino: OK,EXP=ohms-law
```

Осыдан кейін Arduino барлық measurement пакеттерінде дәл осы `EXP`
мәнін қолданады:

```
EXP=ohms-law,U=5.024
```

**Неге B нұсқасы (PC-жақта EXP-ті "routing" қабатымен қосу) емес:**
Егер PC әрбір келген raw жолға EXP-ті өзі "жапсырса", 6-бөлімдегі EXP
mismatch тексерісі (`ExperimentController._process_line`) мағынасын
жоғалтады — PC әрқашан "дұрыс" EXP қоятын болғандықтан, Arduino
шынымен басқа/ескі тәжірибенің деректерін жіберіп жатса да ешқашан
байқалмас еді. `SET_EXP` арқылы EXP әлі де Arduino-дан келеді, demек
mismatch тексерісі толық мағынасын сақтайды.

**Backward compatibility:** `HELLO?`/`TYPE=HELLO` хаттамасы мүлдем
өзгерген жоқ. Ескі firmware (`SET_EXP`-ті танымайтын) команданы жай
елеусіз қалдырады — Arduino құламайды, тек өз ішінде хардкодталған
(немесе әдепкі) EXP-ті жібере береді. `OK,EXP=` жауабы да міндетті
емес: PC оны алмаса, ешбір қате шықпайды (тек 6-бөлімдегідей EXP
mismatch warning-і болуы мүмкін, ол дегеніміз — firmware ескі не
SET_EXP-ті орындамады).

**Start/Stop команда протоколға қосылмады:** қазіргі архитектурада
`ExperimentController` Serial-ға Start/Stop командасын ешқашан
жібермейді — Arduino өлшеуді үздіксіз жібере береді, ал
`ExperimentController` тек өзінің ішкі `running` флагі `True` кезінде
ғана пакеттерді Measurement-ке айналдырады (`running=False` кезінде
пакет "өткізіп жіберілді" деген warning-пен тасталады). Бұл V1.0-мен
бірдей әрекет — осы кезеңде өзгертілген жоқ.

## 13. Multi-device: бірнеше физикалық сенсордан келген каналдарды біріктіру

Нақты hardware құрылымында Voltage/Current/Energy/Ohmmeter — әрқайсысы
**жеке Arduino, жеке COM-порт**. Ohm's Law секілді тәжірибелер (R=U/I)
екі каналды да (voltage, current) талап еткендіктен, екі сенсор бір
мезгілде қосылып тұруы керек:

```
COM3 (Voltage Sensor):  EXP=ohms-law,U=5.024
COM4 (Current Sensor):  EXP=ohms-law,I=0.218
```

Бұл екі бөлек Serial ағынын PC-жақта
`modules/electricity/multi_sensor_experiment_coordinator.
MultiSensorExperimentCoordinator` біріктіреді: әр порттың `PacketParser`
ағыны тәуелсіз жұмыс істейді (EXP/SET_EXP хаттамасы осы құжаттың
11/12-бөлімдерімен бірдей, өзгеріссіз, әр портқа бөлек қолданылады),
ал партиалды мәндер `domain.services.channel_aggregator.ChannelAggregator`
арқылы "соңғы белгілі мән + staleness терезесі (әдепкі 500 мс)"
тәсілімен бір толық жиынтыққа айналады. Толық жиынтық болғанда ғана
(барлық қажетті канал 500 мс ішінде жаңа болса) `DataValidator`/
`CalculationEngine`-ге беріледі — партиалды (мыс., тек voltage) мән
ешқашан валидацияға тікелей жетпейді.

Толық архитектуралық талдау: `MultiSensorExperimentCoordinator`
docstring-і және жоба тарихындағы "Multi-Device Sensor Architecture
Audit" (chat-те бөлек жіберілген).

