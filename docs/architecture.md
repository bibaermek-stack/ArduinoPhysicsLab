# Arduino Physics Lab — архитектура (кодқа сай)

Нұсқа: desktop `0.9.0` (`core/version.py`). Бұл файл **жұмыс істеп тұрған
репозиторий құрылымын** сипаттайды. Ескі жоспардағы JSON-сақтау,
`modules/thermal|magnetic|optics` жолдары және «тек CSV/Excel» мұнда
жоқ.

Толық sync/деплой/хаттама: [sync_architecture.md](sync_architecture.md),
[deployment.md](deployment.md), [serial_protocol.md](serial_protocol.md).

## Екі бөлек өнім

```
Windows .exe (PySide6)                    FastAPI (server/)
  жергілікті SQLite                         Postgres немесе SQLite
  Arduino USB Serial                        JWT + X-API-Key
  sync outbox  ──────── HTTP ────────────►  /api/v1/sync/*
                                            / (Jinja сайт: кіру, жүктеу)
```

- Desktop `server/` кодын іске қоспайды (`app.py` тек клиент).
- Сервер `server.run` / Railway арқылы бөлек процесс.

## Қабаттар (desktop)

```
ui/               PySide6 беттер, виджеттер, ThemeManager QSS
domain/           entity, интерфейстер, CalculationEngine, DataValidator, sync_engine
infrastructure/   Serial, SQLite репозиторийлер, HTTP sync клиент, экспорт адаптерлері
modules/          физика каталогы (ExperimentDefinition)
firmware/         voltage_sensor / current_sensor (Arduino)
core/             нұсқа, тұрақтылар, жолдар, лог
```

DI container жоқ: `app.py` мен `ui/main_window.py` қолмен байланыстырады.
Оқиғалар — Qt signals/slots.

`infrastructure/storage/json_session_repository.py` — пайдаланылмайтын
ескі stub; сессиялар `SqliteSessionRepository` арқылы сақталады.

## Сақтау

Жергілікті дерекқор: `%LOCALAPPDATA%\ArduinoPhysicsLab\...` SQLite
(`infrastructure/storage/database.py`).

Негізгі репозиторийлер (`infrastructure/storage/sqlite_*.py`):

| Репозиторий | Не сақтайды |
|---|---|
| `SqliteSessionRepository` | тәжірибе сессиялары мен өлшемдер |
| `SqliteMeasurementBatchRepository` | cloud sync chunk-тары |
| `SqliteClassroomRepository` / `SqliteStudentRepository` / `SqliteTeacherRepository` | сынып, оқушы, мұғалім |
| `SqliteFeedbackRepository` / `SqliteQuestionRepository` | кері байланыс, сұрақтар банкі |
| `SqliteSyncOutboxRepository` | офлайн outbox (кейін серверге push) |
| `SqliteStudentProgressRepository` | оқушы прогресі |

Сервер жағы: `DATABASE_URL` (Railway-де Postgres) немесе жергілікті SQLite.

## Экспорт

`domain/interfaces/i_exporter.py` → нақты іске асырулар:

- `domain/services/csv_exporter.py`
- `domain/services/excel_exporter.py`
- `domain/services/pdf_exporter.py`

Таңдау: `infrastructure/export/exporter_factory.py`
(`csv` / `xlsx` / `pdf`).

## Физика модульдері

Тіркеу `app.py` ішінде, каталог қалталары:

| Каталог | UI атауы | Күйі |
|---|---|---|
| `modules/heat/` | Жылу құбылыстары | каталог, `is_implemented=False` |
| `modules/electricity/` | Электр құбылыстары | 5 жұмыс істейтін тәжірибе + температура тәжірибесі жоспарлы |
| `modules/electromagnetism/` | Электромагниттік құбылыстар | каталог, `is_implemented=False` |
| `modules/light/` | Жарық құбылыстары | каталог, `is_implemented=False` |

Жоқ жолдар: `modules/thermal`, `modules/magnetic`, `modules/optics`.

Барлық ашылатын тәжірибе `ExperimentWorkspacePage` + `ExperimentDefinition`.
Электр өлшеу ағыны: Serial → `PacketParser` → `DataValidator` →
`CalculationEngine` → `ExperimentSession` (көп құрылғыда
`MultiSensorExperimentCoordinator`).

## Desktop UI (рөл бойынша)

Рөл `RoleSelectionPage` / аккаунт арқылы бір рет таңдалады.

**Оқушы:** басты бет, зертханалар, менің нәтижелерім, кері байланыс, профиль.

**Мұғалім:** бақылау тақтасы, сыныптар, нәтижелер, деректер журналы,
кері байланысты тексеру, аналитика, сұрақтар банкі, құрылғылар, баптаулар.

Навигация кестесі: `ui/navigation/navigation_config.py`.

## Cloud sync

Клиент: `domain/services/sync_engine.py` + `infrastructure/sync/sync_worker.py`.
Офлайн жазбалар outbox-қа түседі, байланыс барда push/pull.

Сервер: FastAPI `server/app/` — `/api/v1/auth`, `/api/v1/sync`, аккаунттар,
Jinja сайт (`server/app/web/`).

## Firmware

- `firmware/voltage_sensor/` — `SENSOR=VOLTAGE`, `U=`
- `firmware/current_sensor/` — `SENSOR=CURRENT`, `I=`

Тақтай сынағы: [hardware_test_guide.md](hardware_test_guide.md).
