# Deployment guide

Phase 9 (Production Deployment, Multi-PC Release Readiness &
Configuration) release documentation. This covers running Arduino
Physics Lab on real, separate Windows PCs — a teacher's PC and one or
more student PCs — talking to one central sync server, instead of the
single developer machine every earlier phase ran on.

## 1. Architecture

```
STUDENT PC                              TEACHER PC
Arduino/sensors (USB)                   —
    ↓
ArduinoPhysicsLab.exe  ←── local SQLite ──→  ArduinoPhysicsLab.exe
    ↓ (when internet available)                    ↑
    └──────────→  Central sync server  ←────────────┘
                  (FastAPI, separate deployment unit)
```

Two independent deployment units:

- **Desktop client** — one packaged `ArduinoPhysicsLab.exe` per PC
  (teacher or student), each with its own local SQLite database. Works
  fully offline; syncs automatically when the server is reachable
  (Phase 5 connectivity-aware sync — unchanged by Phase 9).
- **Central server** — a separate FastAPI process (`server/`), never
  bundled inside the desktop `.exe`, deployed once, shared by every
  client.

## 2. Desktop installation / package

Build a single-file Windows executable:

```powershell
pip install -r requirements.txt -r requirements-build.txt
python -m PyInstaller build\app.spec --distpath release --workpath build\work --noconfirm
```

Output: `release/ArduinoPhysicsLab.exe` (onefile, no `_internal` folder).
Copy that file to the target PC — Python is not required there.

Windows Defender often flags an **unsigned** PyInstaller onefile as a
virus. That is a false positive. The download page explains how to
Allow the file in Protection history. A paid Authenticode certificate
is the only durable fix for SmartScreen.

## 3. Server deployment

Separate machine/service from every desktop client:

```bash
pip install -r server/requirements.txt
# Postgres only (optional, see §10):
#   pip install -r server/requirements-postgres.txt
uvicorn server.app.main:app --host 0.0.0.0 --port 8000
```

Put a reverse proxy with a valid TLS certificate in front of this for
any real internet deployment (see §9). `server/app/main.py` exposes
`GET /api/v1/health` for a liveness check.

## 4. Configuration

Desktop client settings persist per-user via `QSettings` (Windows
registry, `HKCU`) through `infrastructure/storage/app_preferences.py`
— already built in Phase 3/4/5, unchanged in shape by Phase 9:

| Setting | Default | Notes |
|---|---|---|
| Sync server URL | `http://127.0.0.1:8000` | must be `http://` or `https://` — anything else is rejected (§9) |
| Sync enabled | `false` | |
| Request timeout | `5.0`s | |
| Connectivity check interval | 12s | |
| Teacher auto-refresh interval | 10s | |
| Active-experiment sync interval | 10s | |
| Measurement batch chunk size | 250 | |

There is currently no in-app UI to edit the server URL (Settings shows
sync **status**, not a URL editor) — set it via
`AppPreferences.set_sync_api_base_url(...)` from a small provisioning
script, or directly in the registry
(`HKCU\Software\ArduinoPhysicsLab\ArduinoPhysicsLab`, key
`sync/api_base_url`) before first launch on each PC.

## 5. Environment variables (server only)

| Variable | Purpose | Required in production |
|---|---|---|
| `APL_JWT_SECRET` | JWT signing secret | **Yes on Railway/production** — process refuses to start if the public dev placeholder is still in use |
| `APL_SYNC_API_KEY` | Shared `X-API-Key` gate | **Yes on Railway/production** — same hard failure |
| `DATABASE_URL` | SQLAlchemy connection string | No — defaults to a local SQLite file if unset |

None of these are read by the desktop client — it has no server-side
secrets.

## 6. Runtime data directories (desktop)

Nothing writable lives beside `ArduinoPhysicsLab.exe`:

- **Database**: `%LOCALAPPDATA%\ArduinoPhysicsLab\ArduinoPhysicsLab\arduino_physics_lab.db`
  (`infrastructure/storage/database.py::get_default_database_path()`).
  Phase 1-8 used `%APPDATA%` (Roaming) instead — Phase 9 switched to
  `%LOCALAPPDATA%` because an ever-growing SQLite file is a poor fit
  for roaming profiles on a school Windows domain. A safe, additive,
  one-time **copy** (never a move, never a delete) migrates an
  existing Roaming database to the new Local path automatically on
  first launch after upgrading; the old file is left untouched.
- **Preferences / auth token**: Windows registry, `HKCU\Software\ArduinoPhysicsLab\ArduinoPhysicsLab`.
- **Logs**: `%LOCALAPPDATA%\ArduinoPhysicsLab\logs\debug.log`, rotating
  at 2 MB with 3 backups (`core/logging_setup.py`).

## 7. Offline behavior

Non-negotiable and unchanged by Phase 9: the app launches, a valid
local login works, an Arduino experiment runs, measurements/feedback
persist locally, and the outbox queues pending sync rows — all with
zero network requirement. Verified for this phase via
`tests/integration/test_phase9_multi_pc_isolation.py`, which runs a
student PC through an entire measurement session with **no sync calls
at all** during that window, then confirms every row survived an
app-restart-equivalent (rebuilt repositories against the same on-disk
file) before syncing catches up.

## 8. Remote-server configuration

Do not hardcode `localhost` for a real deployment. Point each
installation's `sync/api_base_url` at your server's real address, for
example (illustrative only — replace with your own domain):

```
https://your-school-sync-server.example
```

## 9. HTTPS requirement

The desktop client's HTTP layer (`httpx`, via `HttpSyncApiClient`)
uses standard certificate verification with **no** `verify=False`
anywhere in the codebase (confirmed by repo-wide audit) — it will
reject an invalid/self-signed certificate exactly like a browser
would. `AppPreferences.set_sync_api_base_url()` further rejects any
URL that isn't `http://` or `https://`. Real internet deployment
**requires** the server to sit behind a reverse proxy with a valid
TLS certificate (e.g. Let's Encrypt via nginx/Caddy) — this project
does not implement or manage TLS itself.

## 10. PostgreSQL notes

`server/app/db/session.py` reads `DATABASE_URL` and only applies the
SQLite-specific `check_same_thread` connect argument when the URL
scheme is `sqlite` — the SQLAlchemy layer is structurally dual-capable.
**Not deployed or required for this phase**: no live Postgres instance
was stood up or tested against; tests remain on SQLite throughout. To
use Postgres in production: `pip install -r server/requirements-postgres.txt`
and set `DATABASE_URL=postgresql://...`.

## 11. Logs

Rotating file at `%LOCALAPPDATA%\ArduinoPhysicsLab\logs\debug.log` —
startup diagnostics (version, log/DB paths, frozen-mode flag), a
one-line record of the database path, navigation trace, and any
uncaught exception's full traceback (via `sys.excepthook`, never shown
directly to the student — see §13 crash safety in the Phase 9 report).
**Never logged**: JWT tokens, PIN/access-code hashes, API keys, full
feedback text — confirmed by code audit; the only diagnostic content
is metadata (paths, counts, status strings).

## 12. Troubleshooting

- **App won't start** — check `%LOCALAPPDATA%\ArduinoPhysicsLab\logs\debug.log`
  for the startup block; it records cwd, script path, `frozen` flag,
  and the resolved database path.
- **"Database not reachable" in Settings → ДЕРЕКТЕР** — the file at
  the shown path doesn't exist yet; check disk space and that
  `%LOCALAPPDATA%\ArduinoPhysicsLab\` is writable for the current
  Windows user.
- **Sync never succeeds** — check Settings → БҰЛТТЫҚ СИНХРОНДАУ for the
  live status/error text; confirm the configured server URL (§4) is
  reachable and its certificate is valid (§9) from that PC.

## 13. COM / Arduino troubleshooting

Device discovery uses `PySide6.QtSerialPort` directly (no `pyserial`,
no external driver process) — see the existing in-app "Жиі кездесетін
мәселелер" (Common Issues) section on the Анықтама/Help page, which
already documents: cable reconnection, the Devices page's "Жаңарту"
(refresh) button, and confirming the correct COM port/sensor pairing.
Nothing about packaging changes this — `QtSerialPort` ships as part of
the bundled Qt libraries, no separate driver install is required.

## 14. Backup / update behavior

- **Program files are replaceable.** Reinstalling/upgrading means
  replacing the entire `release/ArduinoPhysicsLab/` folder contents —
  nothing meaningful is ever stored there.
- **User runtime data is persistent** and lives entirely outside that
  folder (§6) — an upgrade that only replaces the program folder
  cannot touch the database, registry preferences, or logs. No
  destructive auto-reset exists anywhere in the startup path.

## 15. Teacher/student multi-PC scenario

End-to-end verified by `tests/integration/test_phase9_multi_pc_isolation.py`:
two fully isolated on-disk SQLite databases (never a shared file),
configured against one shared server — student logs in, runs an
experiment, syncs; teacher receives the data through the server and
sees it in both classroom monitoring (Phase 6) and per-student
analytics (Phase 8); teacher sends feedback (Phase 7) that reaches the
student; the student goes offline and keeps working; both
installations "restart" (repositories rebuilt from the same files);
the server "returns" and both resync with zero duplicate rows; an
unrelated/unauthorized teacher on a third isolated installation sees
none of it.
