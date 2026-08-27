# Arduino Physics Lab — Архитектура (V1.0)

## Жалпы көзқарас

Жоба үш қабатты жеңілдетілген архитектурамен құрылады:

```
ui/              — PySide6 беттер мен виджеттер (view)
domain/          — таза бизнес-логика: entity, интерфейс, сервистер
infrastructure/  — Serial байланыс, экспорт, файлдық сақтау
```

Бөлек Application қабаты және DI container қолданылмайды — объектілер
`app.py`/`main_window.py` ішінде қолмен байланыстырылады (manual wiring).
Модульаралық/ағынаралық байланыс тікелей Qt `signals/slots` арқылы
жүзеге асады (жеке EventBus жоқ).

## Негізгі принциптер

- **Модульдік:** әр физикалық сала (`modules/electricity`, болашақта
  `modules/thermal`, `modules/magnetic`, `modules/optics`) — жеке модуль.
  Модульдер `modules/module_registry.py` ішінде қолмен тіркеледі
  (автоматты plugin discovery жоқ).
- **Ортақ жұмыс беті:** барлық зертхана жұмыстары
  `ui/pages/experiment_workspace_page.py` бетін қолданады, тек
  `ExperimentDefinition` конфигурациясы арқылы ерекшеленеді.
- **Жеңіл контроллер:** әр модульдің `experiment_controller.py` файлы
  Serial-дан келген деректі қабылдап, `DataValidator` пен
  `CalculationEngine` арқылы өңдеп, нәтижені `Measurement` ретінде
  `ExperimentSession`-ға қосады және UI-ге Qt signal арқылы жібереді.
  `ExperimentWorkspacePage` тек осы сигналға жазылып, интерфейсті
  жаңартады (валидация/есептеу логикасы бетте жоқ).
- **Serial байланыс:** `infrastructure/serial_comm/` ішінде бөлек
  `QThread`-та жұмыс істейді. `QSerialPort` объектісі тек worker
  thread ішінде құрылады және қолданылады, UI онымен тек
  `SerialThreadController` арқылы, signal/slot негізінде байланысады.
- **Сақтау:** V1.0-де `JsonSessionRepository` (JSON файл) қолданылады,
  `IMeasurementRepository` интерфейсі арқылы кейін `SqliteRepository`
  ауыстырылып қосылады.
- **Экспорт:** V1.0-де тек CSV және Excel (`IExporter` интерфейсі
  арқылы), PDF кейінгі кезеңде қосылады.

## Кеңейту нүктелері

| Кеңейту | Қосылатын жер |
|---|---|
| SQLite | `infrastructure/storage/sqlite_repository.py` (`IMeasurementRepository`) |
| PDF экспорт | `infrastructure/export/pdf_exporter.py` (`IExporter`) |
| Жылу/Магнит/Жарық модульдері | `modules/thermal/`, `modules/magnetic/`, `modules/optics/` + `module_registry.py`-ге тіркеу |

Толық серия-хаттама сипаттамасы үшін [serial_protocol.md](serial_protocol.md)
файлын қараңыз.
