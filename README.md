# Arduino Physics Lab

Windows desktop зертхана (PySide6) және бөлек FastAPI sync/сайт.
Arduino USB Serial арқылы кернеу/ток өлшеу, график, SQLite, CSV/Excel/PDF
экспорт, мұғалім/оқушы рөлдері, офлайн-first cloud sync.

Нұсқа: **0.10.2**. Магистрлік диссертацияның бағдарламалық платформасы.

## Не істейді (қазіргі код)

| Бөлік | Күйі |
|---|---|
| Электр тәжірибелері (5) + кернеу/ток firmware | жұмыс істейді |
| Температура тәжірибесі (метал кедергісі) | каталогта «Жоспарланған», firmware жоқ |
| Жылу / электромагнит / жарық | каталогта бар, бастауға болмайды |
| Мұғалім панелі, сыныптар, аналитика, сұрақтар банкі | desktop UI-да бар |
| Жергілікті SQLite | бар (`JsonSessionRepository` қолданылмайды) |
| Экспорт CSV / Excel / PDF | бар |
| Sync outbox + `server/` FastAPI | бар |
| Веб-сайт (кіру, Google, .exe жүктеу) | `server/app/web/` |

Толық карта: [docs/architecture.md](docs/architecture.md).

## Репозиторий құрылымы

```
ui/               desktop интерфейс
domain/           бизнес-логика
infrastructure/   Serial, SQLite, HTTP sync
modules/          heat, electricity, electromagnetism, light
firmware/         voltage_sensor, current_sensor
server/           FastAPI API + сайт (desktop-қа араласпайды)
docs/             архитектура, sync, деплой, хаттама
```

## Іске қосу

Desktop (Python ортасында):

```text
pip install -r requirements.txt
python main.py
```

Windows .exe: `build/build.ps1` → `release/ArduinoPhysicsLab.exe`.

Сервер:

```text
pip install -r server/requirements.txt
python -m server.run
```

Production-да `APL_JWT_SECRET` және `APL_SYNC_API_KEY` міндетті
([docs/deployment.md](docs/deployment.md)).

## Құжаттар

- [docs/architecture.md](docs/architecture.md) — қабаттар, сақтау, модульдер
- [docs/serial_protocol.md](docs/serial_protocol.md) — Arduino ↔ PC хаттамасы
- [docs/sync_architecture.md](docs/sync_architecture.md) — outbox / API
- [docs/hardware_test_guide.md](docs/hardware_test_guide.md) — тақтай сынағы
- [LICENSE](LICENSE) — MIT
