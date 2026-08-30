# Recovery guide

Basic facts needed to restore or verify this project from a clean
machine. No secrets are stored here — see the "Secrets" note at the
bottom.

## Authoritative project path

```
D:\Desktop\ArduinoPhysicsLab
```

The Windows Desktop Known Folder was redirected from `C:\Users\User\
Desktop` to `D:\Desktop` at some point in this project's history — if
`[Environment]::GetFolderPath('Desktop')` in PowerShell ever points
somewhere else again, that is the authoritative location, not this
path literally.

## Git basics

The project is a local Git repository (`main` branch, no remote
configured). Stable baselines, oldest to newest (each is a superset of
the previous one's tracked source):

- **Tag:** `v0.6.0-phase6-stable` — Phase 1–6 complete, 2536 tests
  passed (2454 local + 82 server), 0 failed/errored/skipped.
- **Tag:** `v0.7.0-phase7-stable` — Phase 1–7 complete (teacher
  feedback notes, session-history drill-down).
- **Tag:** `v0.8.0-phase8-stable` — Phase 1–8 complete (per-student
  learning progress, weak/strong topic identification, teacher
  dashboard alerts, CSV gradebook export).
  2635 tests passed (2542 local + 93 server), 0 failed/errored/skipped.
- **Tag:** `v0.9.0-phase9-stable` — Phase 1–9 complete (production
  Windows packaging, per-user runtime data directory, resource-path
  abstraction, server production configuration, multi-PC isolation
  acceptance test). **Current recovery point.**
- To inspect a tag: `git show v0.9.0-phase9-stable --stat`
- To restore the working tree to the current baseline:
  `git checkout v0.9.0-phase9-stable` (or `git reset --hard
  v0.9.0-phase9-stable` if you want `main` to point there again —
  only do this if you understand it discards later commits).
- To see what changed since the current baseline: `git diff
  v0.9.0-phase9-stable..HEAD`

## External backup

ZIP snapshots of each tagged commit live outside the project
directory, so a working-directory-level accident (like the Desktop
redirect confusion that prompted the first one) can't take them out
too:

```
D:\ArduinoPhysicsLab_Backups\ArduinoPhysicsLab_Phase1-6_v0.6.0_2026-08-13.zip
D:\ArduinoPhysicsLab_Backups\ArduinoPhysicsLab_Phase1-8_v0.8.0_2026-08-13.zip
D:\ArduinoPhysicsLab_Backups\ArduinoPhysicsLab_Phase1-9_v0.9.0_2026-08-13.zip
```

Each is built via `git archive` from its matching tag, so it contains
exactly that tag's tracked source tree — no `.venv`, no caches, no
logs. Extract and `pip install -r requirements.txt` into a fresh
virtualenv to get a working copy without needing Git at all. The
current baseline is the `v0.9.0` ZIP; earlier ZIPs are kept only as
historical recovery points and were never modified/overwritten when a
newer one was added.

**Note:** this ZIP is a *source* recovery archive only — it does not
contain a built `.exe`. To reproduce the packaged Windows release from
it, follow §2 "Desktop installation/package" in `docs/deployment.md`
after extracting.

## Recreating the Python environment

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

The FastAPI server side also needs its own dependencies — check
`server/` for any additional requirements file before running it.

## Correct test invocation

Run the local suite and the server suite as **two separate pytest
invocations**, not one combined command:

```bash
python -m pytest tests/ -q
python -m pytest server/tests -q
```

Combining them (`pytest tests/ server/tests -q`) produces spurious
`ImportError`s in `server/tests` — a module-resolution collision
between the two same-named `tests` directories, neither of which uses
`__init__.py`, with no root `conftest.py`/`pytest.ini` to disambiguate
them. This is a test-invocation artifact, not a code defect — keep
using two separate commands.

### `tests/unit` on Windows: run it under pytest-xdist

`tests/unit` alone is ~2600 tests, several hundred of which build real
`QWidget`/`pyqtgraph.PlotWidget` trees. Even with the `close()` +
`deleteLater()` teardown in `tests/unit/conftest.py`, running the whole
folder in a single process can still hit a Windows-only native crash
(`Windows fatal exception: 0xc0000374` / `access violation` — Qt/GC
heap corruption, not a Python exception, so pytest can't catch or
report it) somewhere in the run — the exact test that trips it isn't
stable between runs. Install `requirements-test.txt` once, then always
run `tests/unit` distributed by file:

```bash
pip install -r requirements-test.txt
python -m pytest tests/unit -q -n auto --dist=loadfile
```

`--dist=loadfile` keeps each test *file* on one worker (so file-scoped
`qt_application` fixtures still behave). If a worker crashes, xdist
prints `[gwN] node down: Not properly terminated`, marks the in-flight
test as failed, and the rest of the suite keeps running — a single
`python -m pytest tests/unit -q` (no `-n`) run stops dead at the crash
and everything after it never executes, which looks like a much bigger
failure than it is.

## Runtime data location (installed/packaged app, Phase 9+)

This section is about *end-user* installations, not this source
checkout. A running app's actual data (separate from the source
recovery above) lives at:

- Database: `%LOCALAPPDATA%\ArduinoPhysicsLab\ArduinoPhysicsLab\arduino_physics_lab.db`
  (Phase 1-8 used `%APPDATA%` — Roaming — instead; an automatic,
  additive, non-destructive one-time copy migrates an existing Roaming
  database to the new Local path on first Phase 9+ launch, and the old
  Roaming file is left in place).
- Preferences/auth token: Windows registry, `HKCU\Software\ArduinoPhysicsLab\ArduinoPhysicsLab`.
- Logs: `%LOCALAPPDATA%\ArduinoPhysicsLab\logs\debug.log` (rotating).

Full deployment/runtime details: `docs/deployment.md`.

## Secrets

None are stored in this repository or in this document. `APL_JWT_
SECRET` and `APL_SYNC_API_KEY` are read from environment variables at
runtime (see `server/app/services/auth_service.py` and `server/app/
api/deps.py`); if unset, the server falls back to obvious, clearly
non-production placeholder values for local development only. Set
real values via environment variables before any non-local deployment
— never commit them.
