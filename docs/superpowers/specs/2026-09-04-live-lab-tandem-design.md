# Тірі зертхана: сайт + `.exe` тандем

Нұсқа: desktop жоспары `0.10.5` кейінгі кезең. Бұл құжат **бекітілген
шешімдерді** сипаттайды — іске асыру осыған сай жүреді.

## 1. Мақсат

Оқушы сайттан зертхананы ашады, Windows `.exe` толық терезеде өлшейді,
ал **сол өлшемдер ~0.5–1 с ішінде** сайттағы графикте де көрінеді.
Мұғалім қабылданған оқушының тірі графигін сайттан бақылайды.

Басқару (START/STOP, COM-порт, тәжірибе баптауы) тек `.exe`-де қалады.

## 2. Бекітілген шешімдер

| Тақырып | Шешім |
|---|---|
| Оқушының негізгі орны | Сайт кабинеті + `.exe` толық зертхана терезесі |
| Басқару | Тек `.exe` |
| Тірілік | ~0.5–1 с, жаңа ағын (журналдық sync емес) |
| Транспорт | Екі жақты WebSocket (`wss://`) |
| Жұптастыру | Сол email/Google JWT, жаңа PIN жоқ |
| `.exe` ашу | `arduinolab://open` deep link |
| Журнал | Бар `sync_worker` өзгеріссіз |

## 3. Арнайы емес (v1-де жоқ)

- Сайттан START/STOP / COM таңдау
- Браузердің `ws://127.0.0.1` агенті (Chrome PNA/HTTPS бөгеуі)
- 6 таңбалы сессия PIN-і
- Тірі нүктелерді Postgres-ке ұзақ сақтау
- Redis / бірнеше Railway replica арасында pub/sub
- Мобильді қосымша
- `?experiment=` deep-link параметрі (кейін)

## 4. Архитектура

```
Arduino USB
    → .exe  (толық UI, START/STOP, жергілікті график, SQLite)
         ├─ sync_worker          → /api/v1/sync/*     (журнал)
         └─ LiveStreamWorker     → /api/v1/live/ws    (тірі)
                    ↓
              Railway (бір процесс, in-memory hub)
                    ↓
         браузер WebSocket (оқушы: өз ағыны, мұғалім: сынып)
```

Тірі ағын мен журнал **екі бөлек жол**. Тірі нүкте жоғалса, есеп
бұзылмайды — sync batch қалады.

Railway-де **бір инстанс** қажет: хаб процестің жадында. Екінші replica
қосылса, мұғалім басқа процесске түсіп, тірі графикті көрмеуі мүмкін.
v1-де replica саны 1.

## 5. WebSocket хаттамасы

URL: `GET /api/v1/live/ws` (upgrade).

Клиент түрлері: `desktop` (жіберуші), `viewer` (браузер).

### Аутентификация

- Браузер: сол origin cookie `apl_web_token`.
- `.exe`: бірінші кадр `{"type":"auth","token":"<account JWT>"}`.
  Токен access-log query-да қалмасын деп URL-ге жазылмайды.
- `X-API-Key` desktop үшін auth кадрында: `{"type":"auth","token":"...","api_key":"..."}`.
  Браузерге API кілт керек емес (cookie + origin).

Сәтсіз auth → close 4401.

### Кадрлар (JSON)

Desktop → сервер:

```json
{"type":"auth","token":"...","api_key":"..."}
{"type":"status","state":"idle|measuring","experiment_id":"ohms-law"}
{"type":"samples","experiment_id":"ohms-law","session_id":"...",
 "points":[{"t":"2026-09-04T12:00:00.123Z","values":{"voltage":1.2,"current":0.01}}]}
{"type":"ping"}
```

Сервер → viewer:

```json
{"type":"hello","role":"student|teacher"}
{"type":"presence","account_id":"...","public_id":"S-...","display_name":"...","state":"idle|measuring|offline"}
{"type":"samples","account_id":"...","experiment_id":"...","points":[...]}
{"type":"error","detail":"..."}
{"type":"pong"}
```

Сервер → desktop (v1-де тек қызметтік; START жоқ):

```json
{"type":"hello","role":"student|teacher"}
{"type":"pong"}
```

`type":"command"` кадры хаттамада **резерв**, v1 өңдемейді.

### Шектеулер

- Бір `points` массивінде ең көбі 50 нүкте.
- Бір desktop қосылымынан ең көбі ~20 нүкте/с; артығы тасталады.
- Сервер буфері: оқушы сайын соңғы ~120 с (viewer кейін қосылса, қисық
  бос емес).
- `values` кілттері desktop `Measurement.values` / `derived_values`
  атауларымен бірдей (`voltage`, `current`, …).

## 6. Сервер

Жаңа модульдер (ұсыныс):

- `server/app/api/live.py` — WebSocket route
- `server/app/services/live_hub.py` — in-memory қосылымдар мен буфер
- `server/tests/test_live_ws.py`

Кімге не жіберіледі:

- Desktop student auth болса, хаб оны `account.id` астына **publisher**
  қылады. Бір оқушыда бір ғана белсенді desktop; жаңасы ескіні үзеді.
- Viewer student: тек өз `account.id` ағыны.
- Viewer teacher: `student_link_status` / relationship_links бойынша
  **қабылданған** оқушылар ғана. Дербес оқушы мұғалімге бармайды.
- Рөлсіз аккаунт — 4403.

Сайт беттері (Jinja, қазіргі `app.css`):

| Жол | Кім | Не |
|---|---|---|
| `/lab` | оқушы | күй, график, «Зертхананы бастау» |
| `/monitor` | мұғалім | оқушы тізімі + таңдалған график |

Навигацияға қосылады. Кабинет (`/app`) батырмалар береді.

График: жеңіл JS (Canvas немесе бір файлдық chart, жаңа npm стегі жоқ).
`web/` Vite қосымшасы бұл беттерге қосылмайды.

Cookie-сіз API клиенті (болашақ) үшін viewer де auth кадрын жібере алады.

## 7. Desktop

`SyncWorker` үлгісі: QThread + worker object, GUI ағынында WebSocket жоқ.

- `infrastructure/sync/live_stream_worker.py`
- `infrastructure/sync/live_stream_controller.py`
- Тәуелділік: `websockets` (PySide6 QtWebSockets емес — тест оңай,
  PyInstaller hiddenimport).

Қосылу: аккаунт токені барда және sync base URL барда. Токен жоқ /
шығу → сокет жабылады.

Жіберу көзі: `ExperimentWorkspacePage` / coordinator
`measurement_ready` — бар график жолы. Worker кезекке алады, ~500 мс
сайын бір `samples` кадрын жібереді (бірнеше нүктені біріктіреді).
Өлшеу жоқ кезде 5 с сайын `status: idle` + ping.

Жергілікті график, USB, SQLite **WebSocket күтпейді**. Сокет жабық
болса өлшеу жалғасады.

Бір дана: named local socket / mutex. Екінші іске қосу (соның ішінде
`arduinolab://`) бірінші терезені `showMaximized` + `raise` етеді де
шығады.

## 8. Deep link `arduinolab://`

Бірінші сәтті іске қосуда HKCU (админсіз):

```
HKCU\Software\Classes\arduinolab
  URL Protocol = ""
  shell\open\command = "<exe path>" "%1"
```

v1 URL: `arduinolab://open`

Сайт: `<a href="arduinolab://open">Зертхананы бастау</a>`.
Қолданба жоқ / протокол жоқ: браузер қатесі + беттегі «.exe жүктеу».

PyInstaller onefile: команда нақты `ArduinoPhysicsLab.exe` жолы.
Жаңартылған exe жолы әр іске қосуда жазылады (idempotent).

## 9. Қауіпсіздік

- Тек account JWT (не web cookie). Sync-only teacher/student token
  (`typ` басқа) жеткіліксіз.
- Origin: веб viewer үшін Railway/public base (`APL_PUBLIC_BASE_URL`).
  Desktop origin тексермейді.
- Мұғалім бөтен оқушы `account_id` сұраса — кадр жіберілмейді.
- Тірі буфер құпия емес өлшем; логқа token/api_key/payload мәндері
  жазылмайды (`sync_worker` ережесі).
- HTTPS/WSS production-да. Жергілікті: `ws://127.0.0.1:8000`.

## 10. Сәтсіздіктер

| Жағдай | Мінез-құлық |
|---|---|
| `.exe` жабық | `/lab`: «Қолданбаны ашыңыз», график тоқтайды |
| Желі үзілді | Desktop backoff 1s, 2s, 5s, 10s (max 10s). USB тоқтамайды |
| Viewer үзілді | Хаб publisher-ді ұстайды; қайта кіргенде буфер+жаңа нүкте |
| Токен мерзімі бітті | close 4401; desktop қайта login немесе жаңарту (v1: қолданушы қайта кіреді) |
| Defender протоколды бөгеді | жүктеу бетіндегі Allow нұсқауы; deep link міндетті емес, `.exe`-ні қолмен ашу жеткілікті |

## 11. Тест

- Hub: student samples → сол student viewer; басқа student көрмейді.
- Teacher viewer тек accepted link оқушысын көреді; independent жоқ.
- Auth жоқ / бұзық token → 4401.
- Desktop worker: GUI ағынын блок етпейді (unit, fake socket).
- Deep link register: HKCU жазуын mock-пен (CI-да нақты реестрсіз).
- Регрессия: `/api/v1/sync/*` және оқушы код экранының жоқтығы.

## 12. Файлдар (жоспар)

| Жаңа | Өзгерту |
|---|---|
| `server/app/api/live.py` | `server/app/main.py` router |
| `server/app/services/live_hub.py` | `server/app/web/routes.py` `/lab`, `/monitor` |
| `server/app/web/templates/lab.html` | `base.html` nav |
| `server/app/web/templates/monitor.html` | `dashboard.html` батырмалар |
| `server/app/web/static/live.js` | `requirements.txt` + `websockets` |
| `infrastructure/sync/live_stream_*.py` | `app.py` / `MainWindow` controller |
| `infrastructure/os/protocol_handler.py` | `build/app.spec` hiddenimport |
| `server/tests/test_live_ws.py` | desktop нұсқа bump релиз кезінде |

## 13. Қабылдау критерийі

1. Сайтта оқушы «Зертхананы бастау»-ды басады → `.exe` ашылады (немесе
   алға шығады).
2. `.exe`-де өлшеу басталса, `/lab` графигі 1 с ішінде қозғалады.
3. Мұғалім `/monitor`-да сол оқушыны (қабылданған) көреді.
4. `.exe` офлайн болса да жергілікті өлшеу мен журнал sync жұмыс істейді.
5. Жаңа PIN/код экраны жоқ.
