# Offline-First + Cloud Sync — Architecture (Phase 1 + Phase 2 + Phase 3 + Phase 4 + Phase 5)

This document covers the Phase 1 "Offline-First + Cloud Sync
Foundation" work, the Phase 2 "Experiment Session + Results + Feedback
Cloud Sync" work, the Phase 3 "Production Authentication +
Authorization" work, the Phase 4 "Raw Arduino Measurement Cloud
Sync" work, and the Phase 5 "Connectivity-Aware Automatic Sync +
Near-Real-Time Classroom Monitoring" work: what was built, how to run
it locally, and what remains explicitly deferred to a later,
separately-approved phase.

**Scope of Phase 1**: architecture foundation, sync metadata, local
outbox, a FastAPI server, and a safe first-entity sync (teachers,
classrooms, students, teacher↔classroom relationships).

**Scope of Phase 2**: experiment session metadata, the student↔session
link, student-authored feedback content, and teacher assessments
(score + comment) are synced.

**Scope of Phase 3** (see [§Phase 3](#phase-3-production-authentication--authorization)
below): the Phase 1 shared `X-API-Key` is replaced as the per-user
authorization layer by short-lived JWT access tokens tied to a
specific Teacher/Student identity; every sync route now enforces
server-side ownership rules (a teacher only ever sees their assigned
classrooms/students/sessions, a student only ever sees their own).

**Scope of Phase 4** (see [§Phase 4](#phase-4-raw-arduino-measurement-cloud-sync)
below): the raw, per-sample Arduino measurement rows themselves are now
synced — batched into chunks (not one HTTP request per sample), local-
first (acquisition never waits on the network), idempotent, ordered,
and authorized through the same session-ownership rules as Phase 2/3.

**Scope of Phase 5** (see [§Phase 5](#phase-5-connectivity-aware-automatic-sync--near-real-time-classroom-monitoring)
below): sync is no longer purely manual/periodic-only. A lightweight
connectivity monitor detects when the configured sync server becomes
reachable again and automatically triggers a sync cycle — no manual
"Sync now" press required. An actively running experiment periodically
pushes newly-batched measurements while it runs (reusing Phase 4's
batching, not per-sample requests), and a teacher's app periodically
re-pulls at a much shorter interval than before so new student data
appears within roughly 5–15 seconds under normal conditions. All of
this is built as new triggers into the *existing* `SyncEngine`/
`SyncWorker` — no parallel sync system, no WebSockets.

## 1. Architecture

```
Arduino/Sensor → USB → Desktop App → Local SQLite ⇅ Sync Engine ⇅ HTTPS → FastAPI Server ⇅ (SQLite dev / PostgreSQL prod)
```

The desktop app's local SQLite database remains the source of truth for
UI reads/writes at all times. The app works fully offline; nothing in
the existing UI pages talks to HTTP directly — only
`domain/services/sync_engine.py` does, and only through the
`ISyncApiClient` interface (`infrastructure/sync/http_sync_api_client.py`
is the only concrete implementation).

```
ui/pages/*                  (never call HTTP)
   │  reads/writes via repository interfaces (unchanged)
   ▼
infrastructure/storage/sqlite_*_repository.py
   │  optional sync_outbox_repository param enqueues intent
   ▼
sync_outbox (SQLite table, durable)
   │
infrastructure/sync/sync_thread_controller.py  (QThread, UI-safe)
   │  owns
infrastructure/sync/sync_worker.py             (worker thread, owns SyncEngine)
   │  calls
domain/services/sync_engine.py                 (pure Python, push + pull)
   │  via
infrastructure/sync/http_sync_api_client.py    (httpx)
   │  HTTPS
   ▼
server/app/main.py  (FastAPI, separate process)
   │
server/app/services/sync_service.py
   │
SQLAlchemy models (server/app/models/sync_models.py) → SQLite (dev) / PostgreSQL (prod)
```

## 1a. Manual demo script

`scripts/sync_poc_demo.py` runs the full §30 manual demo end to end
against a **real** `uvicorn` server on a real socket (not the in-process
`TestClient` used by the automated test suite): starts a server on an
isolated temp SQLite file, syncs "Client A" (creates a classroom +
student), syncs "Client B" (confirms the same data arrives), stops the
server and edits data on Client A (confirms the app still works fully
offline), restarts the server, and confirms the pending edit reaches
Client B. Uses only temp files/an ephemeral port — never the real app
database.

```bash
python scripts/sync_poc_demo.py
```

## 2. Running the local server

```bash
pip install -r server/requirements.txt
uvicorn server.app.main:app --reload --port 8000
```

The server never starts as part of the desktop process (`app.py`). By
default it uses a local SQLite file (`server/app/db/session.py::get_database_url()`);
set `DATABASE_URL` to point at PostgreSQL in production — never hardcoded.

Health check: `GET http://127.0.0.1:8000/api/v1/health`.

Auth: every sync route requires header `X-API-Key: <value>`. Read from
env var `APL_SYNC_API_KEY`; falls back to `dev-local-only-key` for local
dev (same convention as `APL_TEACHER_PIN`, see `domain/services/teacher_pin.py`).

## 3. Configuring the client

`infrastructure/storage/app_preferences.py` exposes:

- `get/set_sync_api_base_url()` — default `http://127.0.0.1:8000`.
- `get/set_sync_enabled()` — default **`False`**. Sync is opt-in; until a
  teacher turns it on in Settings → "БҰЛТТЫҚ СИНХРОНДАУ", the worker
  thread performs a periodic no-op and no HTTP requests are made.
- `get/set_sync_request_timeout()` — default 5s.
- `get/set_sync_pull_cursor(entity_type)` — persisted incremental-pull
  cursor per entity type (§18).

## 4. How sync IDs work

- Local primary keys (`Teacher.id` / `Classroom.id` / `Student.id`) are
  already UUID strings and are **never** changed or replaced.
- Each entity has a separate `sync_id: str` field, defaulting to the
  same value as `id` at creation time (`sqlite_*_repository.create()`).
  It exists as a distinct field so a future phase could diverge it from
  the local PK without a schema change.
- Pulled records reuse the sender's `sync_id` as the local `id` when
  first seen on a new device — the same logical record keeps the same
  `sync_id` everywhere (`apply_remote_upsert()` in each repository).

## 5. Sync state

`domain/entities/sync_state.py::SyncState`: `PENDING_UPLOAD`, `SYNCED`,
`PENDING_DELETE`, `CONFLICT`, `ERROR`. Stored per-record
(`sync_state` column). This is distinct from `domain/entities/sync_status.py::SyncStatus`
(`OFFLINE`/`ONLINE`/`SYNCING`/`SYNCED`/`SYNC_ERROR`), which is the
whole-app connectivity/last-sync-result indicator shown in the sidebar,
and distinct from the pre-existing UI `ProgressStatus` (student
experiment progress), which sync code never touches.

## 6. Outbox (local sync queue)

Table `sync_outbox` (`infrastructure/storage/database.py`): durable,
survives app restart. `UNIQUE(entity_type, entity_sync_id)` — a new
`create()`/`update()`/`archive()` call **coalesces** into the existing
pending entry via `INSERT ... ON CONFLICT DO UPDATE` rather than
appending a new one (§7). Repositories enqueue automatically when
constructed with a `sync_outbox_repository` (optional; omitted in all
pre-existing call sites and 2000+ existing tests, so behavior there is
unchanged).

`apply_remote_upsert()` / `mark_synced()` / `apply_remote_assignment()`
on each repository **never** enqueue — they are the "data came from the
server" path, and enqueueing there would create an infinite push↔pull
loop.

## 7. Retry behavior

`domain/services/sync_backoff.py`: fixed schedule 1 / 5 / 15 / 30
minutes, capped at 30 minutes for further attempts. Not exponential, not
per-second — deliberately simple (§17).

## 8. Connectivity / background sync

`SyncEngine.run_sync()` first calls `ISyncApiClient.check_health()`
(2s timeout, never raises). If unreachable, it returns `SyncStatus.OFFLINE`
immediately without touching push/pull — this is the normal offline
path, not an error.

`infrastructure/sync/sync_worker.py` + `sync_thread_controller.py`
follow the exact `SerialWorker`/`SerialThreadController` pattern already
used for serial ports: a `QThread` is only created lazily, all
sqlite3/httpx objects are constructed inside `initialize()` (i.e. inside
the worker thread), and a `QTimer` inside the worker fires
`run_sync_now()` every 15 minutes. `run_sync_now()` no-ops immediately
if `AppPreferences.get_sync_enabled()` is `False`, so an idle worker
thread performs no I/O.

Triggers wired: **startup-after-UI** (`app.py::run()`, right after
`showMaximized()`), **manual** (Settings → "Қазір синхрондау" button →
`MainWindow.trigger_manual_sync()`), and **periodic** (15 min, inside
the worker). Connectivity-restored triggering is not separately wired in
Phase 1 (see [Deferred](#deferred-until-a-later-phase) below) — the
periodic timer will pick up a restored connection within 15 minutes, or
the user can sync manually.

## 9. Sync status UI

Sidebar shows a small subtle label (`Sidebar.set_sync_status_text()`):
"● Синхрондалды" (green) / "● Синхрондалуда..." (amber) / "● Офлайн"
(grey) / "● Синхрондау қатесі" (red). No modal dialogs. Settings page
mirrors the same text with push/pull counts. `MainWindow` is the only
place that knows about `SyncThreadController` — `Sidebar`/`SettingsPage`
stay "dumb display" widgets, matching the existing
`set_active_teacher_text()` convention.

## 10. Conflict strategy (Phase 1)

Server-authoritative, last-write-wins by **server revision**, never by
local clock: each upsert increments a server-side `server_revision`
integer (`server/app/models/sync_models.py`); the client stores the
revision it last saw and always accepts whatever the server currently
returns on pull. No `CONFLICT` state is actually reachable in Phase 1
because there is no concurrent-edit detection yet (single
last-write-wins is the whole strategy) — the `SyncState.CONFLICT` enum
value exists for a future phase that adds real conflict detection
(e.g. comparing server_revision on push).

## 11. First synchronized entities

Ready for sync: **Teacher, Classroom, Student, Teacher↔Classroom
assignment set**. Endpoints: `POST/GET /api/v1/sync/{teachers,classrooms,students,teacher-classrooms}`.
`pin_hash` and `student_code` are included in the synced payload
deliberately (`domain/services/sync_payload.py`) — offline login on a
second device requires them locally; they are never logged
(`sync_engine.py` only logs entity type / counts / error text).

## 12. Authentication (Phase 1 — minimal, not final)

Shared `X-API-Key` header only (`server/app/api/deps.py`). This is a
placeholder guarding sync endpoints from accidental exposure, not a real
per-teacher/per-device auth scheme — that is deferred (see below). Local
PIN/access-code login is completely unaffected: a teacher or student who
has previously synced can still log in with no network at all, because
their `pin_hash`/`student_code` already lives in the local SQLite file.
A brand-new cloud-only account created on a machine that has never
synced **cannot** log in there — this is expected, not a bug, and is
unchanged from local-only behavior.

---

## Phase 2: Experiment Session + Results + Feedback Cloud Sync

### Canonical synchronized records

Per the audit, `StudentExperimentProgress`
(`domain/entities/student_experiment_progress.py`) is **never
persisted** — `SqliteStudentProgressRepository.get_progress()` computes
it fresh on every call from `derive_status()` fed by three inputs. Phase
2 therefore syncs those three authoritative inputs, not a fourth
competing "progress" record — every device's existing
`derive_status()`/`get_progress()` logic runs unchanged and
automatically produces correct progress once its inputs are present
locally, from whichever device the data was created on:

1. **`ExperimentSession`** (table `experiment_sessions`) — session
   metadata (`experiment_id`, `experiment_title`,
   `experiment_display_number`, `started_at`, `ended_at`, `status`,
   `measurement_count`). Raw `measurements` rows are **not** included.
2. **`session_student_link`** — which student performed which session,
   plus the classroom context recorded at the time (historical, not
   re-derived from the student's *current* classroom).
3. **`ExperimentFeedbackResult`** / **`TeacherAssessment`** (table
   `experiment_feedback`) — student-authored 3-level answers/scores,
   and the teacher's score (0–10) + comment. These are two
   *independent* synced entities that happen to share one physical
   local row (see below).

### Entity-relationship (client-side)

```
ExperimentSession (id = entity_sync_id)
        │ 1:1 (by session_id, no FK — a link can exist before/without a session row)
        ▼
session_student_link ── student_sync_id ──▶ Student.id
        │                classroom_sync_id ──▶ Classroom.id
        │ 1:1 (session_id is the PK of experiment_feedback too)
        ▼
experiment_feedback  (ONE physical row, TWO independent sync entities)
   ├─ feedback_result:      level1/2/3 answers, is_draft, submitted_at
   └─ teacher_assessment:   teacher_score, teacher_comment, teacher_reviewed
```

### Why `ExperimentSession`/`ExperimentFeedbackResult`/`TeacherAssessment`
### were *not* widened with sync fields

Unlike `Teacher`/`Classroom`/`Student` in Phase 1 (small, rarely-passed
dataclasses where adding `sync_id`/`sync_state`/`server_revision`
fields was low-risk), `ExperimentFeedbackResult`/`TeacherAssessment` are
threaded through `ResultsPage`, `TeacherFeedbackReviewPage`,
`StudentFeedbackPage`, `StudentResultsPage`, and report dialogs, and
`ExperimentSession` is a transient in-memory object during a live
experiment (pages actually read `SessionSummary`, a separate read-model
that was also left untouched). Widening these would have meant editing
many call sites for no behavioral benefit. Instead, **all sync
bookkeeping lives purely in SQL columns and repository methods**
(`get_*_sync_payload()` / `apply_remote_*()` / `mark_*_synced()` /
`enqueue_*_for_sync()`), and `SyncEngine` talks to those methods
directly — the domain dataclasses that UI pages already use are
byte-for-byte unchanged.

### Session identity / entity_sync_id reuse

None of the four Phase 2 tables gained a separate `sync_id` column.
`ExperimentSession.id` is already a UUID string and is used directly as
its own `entity_sync_id`. `session_student_link` and
`experiment_feedback` are both natively keyed by `session_id`
(`session_id TEXT PRIMARY KEY` on both tables already, pre-Phase-2), so
that same session id is reused as the `entity_sync_id` for
`session_student_link`, `feedback_result`, and `teacher_assessment`
too — no new identifiers were invented.

### Feedback/teacher-assessment split (avoiding cross-device clobber)

Locally, `SqliteFeedbackRepository._save()` (student draft/submission)
and `save_teacher_assessment()` already do careful read-preserve-write
on the *other* half's columns so one never erases the other. Naively
syncing `experiment_feedback` as one whole-row payload would break that
guarantee across devices: if a teacher's device pushes a review before
pulling the student's latest answers, its next push (built from
locally-stale data) would overwrite the server's newer student content.
Phase 2 avoids this by treating `feedback_result` and
`teacher_assessment` as **two independent outbox entity types**, each
with its own `sync_state`/`server_revision` pair
(`experiment_feedback` gained `sync_state`/`server_revision` for the
feedback half and `teacher_sync_state`/`teacher_server_revision` for
the teacher half), and the server mirrors this with a matching
`FeedbackResultRecord` that has two independently-updated column
groups. `server/app/models/sync_models.py::FeedbackResultRecord`
deliberately does **not** use SQLAlchemy's `onupdate=` for either
`updated_at` or `teacher_updated_at` — that would make *any* update to
the row bump *both* timestamps and cause each half's pull to spuriously
re-fetch the other half's unrelated changes. Each `upsert_*()` function
sets only its own timestamp explicitly.

### Dependency ordering

`PUSH_ORDER` (`domain/services/sync_payload.py`) is extended, not
replaced:

```
teacher → classroom → student → teacher_classroom → session → session_student_link → feedback_result → teacher_assessment
```

Unlike `student → classroom` (strict FK, enforced server-side),
`session_student_link`/`feedback_result`/`teacher_assessment` do
**not** require a `sessions` row to exist server-side first
(`server/app/services/sync_service.py` — no FK/existence check on
`session_sync_id`). This is deliberate: locally, `link_session()` is
called at experiment *start*, before any measurement, and an abandoned
experiment can leave a link with no session ever created — this is
already a valid, meaningful state (`derive_status(has_link=True,
measurement_count=0)` → `IN_PROGRESS`). Requiring a session row first
would make ordinary abandoned-then-resumed experiments fail to sync.
`student_sync_id`/`classroom_sync_id` on `session_student_link` **are**
real FKs, since Phase 1 push order guarantees those always exist first.

### Server model

New tables (`server/app/models/sync_models.py`): `sync_sessions`,
`sync_session_links`, `sync_feedback_results` (holds both the feedback
half and the teacher-assessment half of the row, matching the client's
single-table design). New routes (`server/app/api/sync.py`):

```
POST/GET /api/v1/sync/sessions
POST/GET /api/v1/sync/session-students
POST/GET /api/v1/sync/feedback-results
POST/GET /api/v1/sync/teacher-assessments
```

`TeacherAssessmentPayload.score` is validated server-side as `0 ≤
score ≤ 10` (Pydantic `Field(ge=0, le=10)`), matching the existing
local `TeacherAssessment.validate()` scale — no new grading model.
`pull_teacher_assessments()` filters out the empty pre-insert "shell"
row a teacher-assessment-before-feedback push can create
(`teacher_score IS NOT NULL`), so an unscored session never appears in
a teacher-assessment pull.

### Offline lifecycles

- **Student submission**: `link_session()` → `save_session()` →
  `save_submission()` are three independent local SQLite writes/commits
  (as before Phase 2 — no new cross-repository transaction was
  introduced, matching "do not broadly rewrite repositories for
  theoretical purity"). Each queues its own outbox entry the moment it
  commits; none waits on HTTP. If the server is unreachable,
  `SyncEngine.run_sync()` returns `SyncStatus.OFFLINE` and all three
  local writes are already durably saved and queued for the next
  successful sync.
- **Teacher review**: `save_teacher_assessment()` writes locally and
  the UI reflects `REVIEWED` state immediately
  (`SqliteStudentProgressRepository.get_progress()` re-derives it from
  the just-written row) — the outbox entry for `teacher_assessment`
  syncs asynchronously, server outage does not block grading.

### Version compatibility

`SessionPayload.experiment_id` is a free-form string on both client and
server — the server never validates it against `ModuleRegistry` (which
it cannot see; experiment IDs are still 100% code-defined, not
user/DB data, matching Phase 1's audit finding). A newer client
submitting a session for an experiment ID an older teacher-side app
doesn't recognize will not crash or corrupt data: the session still
syncs and displays with whatever generic metadata was sent
(`experiment_title`), only experiment-catalog-specific rendering (e.g.
resolving assessment questions) would be unavailable until that device
upgrades.

### Deferred within Phase 2

- Raw measurement rows (see [below](#deferred-raw-measurements)) —
  `ExperimentSession` sync intentionally reuses the session's own `id`
  as its `entity_sync_id`, so a future measurement-batch-upload phase
  can attach batches to the same identifier without inventing a new one.
- Real per-teacher/per-student server-side authorization scoping (see
  §12/Phase 1 — still a shared `X-API-Key` in Phase 2; the security
  scaffolding vs. production-auth distinction from Phase 1 is unchanged
  and still applies to these new routes).
- Delete/archive semantics for sessions/feedback/assessments: the
  current production UI never deletes a session, feedback result, or
  teacher assessment, so Phase 2 deliberately does not add a remote
  DELETE operation for them (§20 — "do not invent remote DELETE
  behavior blindly"). `session`/`session_student_link`/
  `feedback_result`/`teacher_assessment` outbox entries only ever use
  `OutboxOperation.UPSERT`.

## Phase 2 manual demo

`scripts/sync_poc_demo_phase2.py` runs the full §41 final acceptance
scenario against a real `uvicorn` server on a real socket: seeds and
syncs a shared Teacher/Classroom/Student, has a "student" client
submit a synthetic experiment result, has a "teacher" client pull it
(discovered purely through `IStudentProgressRepository`/
`IFeedbackRepository` — no cloud-only UI code), reviews it (score 9/10
+ a Kazakh comment), syncs the review back to the student, stops the
server mid-flow to prove a second offline submission still saves
locally, restarts the server, and confirms the pending submission
reaches the teacher. Prints a PASS/FAIL summary; uses only temp
files/an ephemeral port/synthetic names.

```bash
python scripts/sync_poc_demo_phase2.py
```

## Phase 3: Production Authentication + Authorization

### Architecture

```
Desktop
   │  local PIN/access-code login (unchanged — hashlib SHA-256, no network)
   ▼
Local SQLite (unchanged source of truth)
   │
Outbox (unchanged)
   │
Authenticated SyncEngine ── get_active_role_and_sync_id / get_cached_token / set_cached_token
   │  (injected callables, same pattern as get_pull_cursor/set_pull_cursor)
   ▼
HttpSyncApiClient ── Authorization: Bearer <JWT>  +  X-API-Key (both, defense in depth)
   │  HTTPS
   ▼
FastAPI: require_api_key()  →  get_current_user()  (decodes/validates JWT)
   │
Authorization layer (server/app/services/authorization.py)
   │  re-resolves current teacher/student ↔ classroom/session ownership on EVERY request
   ▼
Cloud DB (TeacherRecord/StudentRecord ARE the user identities — no separate users table)
```

### Authentication flow

1. **Local login is unchanged.** `RoleSelectionPage` still validates a
   teacher PIN (`domain/services/teacher_pin.py`, SHA-256, `hmac.compare_digest`)
   or a student access code (`IStudentRepository.get_by_code()`)
   entirely offline, exactly as before Phase 3. This is what lets a
   user get into the app with zero network at all.
2. **When `SyncEngine.run_sync()` runs** (background timer, manual
   button, or startup-after-UI — unchanged triggers), it asks the
   injected `get_active_role_and_sync_id()` callable (wired in
   `SyncWorker.initialize()` from `SqliteActiveTeacherRepository`/
   `SqliteActiveStudentRepository` — the SAME tables `RoleSelectionPage`
   already writes on successful local login) who is currently logged
   in locally.
3. If nobody is locally logged in, or the 3 auth callables were never
   supplied to `SyncEngine` (e.g. in older test/script call sites),
   sync proceeds exactly as Phase 1/2 did (auth orchestration is fully
   optional — see [Backward compatibility](#backward-compatibility-with-phase-12)).
4. Otherwise it checks a **cached token** (`AppPreferences.get_sync_auth_token()`,
   `(token, expires_at, role, sync_id)`, QSettings-backed, same
   "no at-rest encryption" level as the existing PIN hash / API key —
   documented limitation, not a new one). If the cache is valid **and**
   was issued to this exact `(role, sync_id)`, it's reused as-is — no
   network call.
5. Otherwise it resolves the **local credential** for that identity —
   `Teacher.pin_hash` or `Student.student_code`, both already sitting
   in the local SQLite row from Phase 1 — and calls
   `POST /api/v1/auth/{teacher,student}-login` with `{sync_id, pin_hash}`
   or `{sync_id, student_code}`. **The raw PIN/access code is never
   sent** — only the already-hashed/already-synced value the server
   already has from `/api/v1/sync/teachers`/`/students` pushes (§2 "Do
   not send plaintext PINs/access codes").
6. The server compares the submitted value against the stored
   `TeacherRecord.pin_hash`/`StudentRecord.student_code` and, on match,
   issues a JWT (`server/app/services/auth_service.py::create_access_token()`).

### Token model / lifecycle

- **HS256 JWT**, signed with `APL_JWT_SECRET` (env var, dev fallback —
  same "opt-in env var + local dev default" convention as
  `APL_TEACHER_PIN`/`APL_SYNC_API_KEY`).
- **Payload**: `{sub: <teacher_or_student sync_id>, role: "teacher"|"student", exp}`.
  Deliberately carries **nothing else** — no classroom list, no
  cached permissions — because `authorization.py` re-resolves current
  assignments from the database on every single request. A classroom
  reassignment or an archived student takes effect on the *next*
  request, not at the next token refresh.
- **60-minute expiry.** No separate refresh-token table: re-authentication
  is just "run the same local-credential login again," which the
  desktop can always do offline-first since it already has the
  credential locally.
- **Dependency added**: `PyJWT` (`server/requirements.txt`) — chosen
  over `python-jose`/`authlib` because only symmetric HS256
  signing/verification is needed, no asymmetric keys.

### Bootstrap / first-time identity (trust-on-first-use)

Existing installations already have local teachers/students/classrooms
with UUID `sync_id`s and PIN/code hashes — Phase 3 does not touch any
of that. The **first** login for a `sync_id` the server has never seen
creates a minimal `TeacherRecord`/`StudentRecord` right then, using the
hash/code submitted in that login request as the new authoritative
value (`auth_service.py::authenticate_teacher()`/`authenticate_student()`).
This is deterministic and idempotent — the same identity's *second*
login just compares against what got stored the first time — and
requires no admin step, no destructive migration, and no local
database rebuild. It's the same trust model as SSH host-key TOFU: the
first device to authenticate as a given identity establishes it;
after that, only the matching credential is accepted.

### Server-side authorization rules

Centralized in `server/app/services/authorization.py`, re-checked on
every request (never cached, never trusted from the client):

| Route pair | Pull (GET) | Push (POST) |
|---|---|---|
| `teachers` | self only | self-`sync_id` only (403 otherwise) |
| `classrooms` | teacher: assigned + *unclaimed* classrooms; student: own classroom | teacher only; if classroom already has an assigned teacher, caller must be a member |
| `students` | teacher: students in visible classrooms; student: self only | teacher only, must be assigned to (or first-claim) the target classroom |
| `teacher-classrooms` | self only | self-`teacher_sync_id` only |
| `sessions` | filtered via the session's `session_student_link` ownership | new session: any authenticated role; existing: must own it |
| `session-students` | teacher: own classrooms; student: self only | student: `student_sync_id` must be self; teacher: must be assigned to the classroom |
| `feedback-results` | filtered via link ownership | **student role only**, must own the session |
| `teacher-assessments` | filtered via link ownership | **teacher role only**, must be authorized for the session's classroom |

Two design points worth calling out:

- **Pulls never hard-reject** — they return a filtered (possibly empty)
  list, always `200`. `SyncEngine._pull_all()` pulls *every* entity
  type in `PUSH_ORDER` every cycle regardless of the local user's
  role (unchanged from Phase 1/2), so a student's routine sync also
  calls `GET /teachers` — hard-403ing that would turn every ordinary
  student sync into a permanent error. **Pushes do hard-403** — a
  legitimate client's outbox only ever contains what its own role
  actually created locally, so a 403 there means either an attack or a
  client bug, and gets surfaced immediately rather than silently
  degraded.
- **"Unclaimed" classrooms** — a brand-new classroom with no
  `teacher-classrooms` assignment yet is visible/writable by any
  teacher, because `session_student_link`/`session`/`classroom` racing
  ahead of `teacher_classroom` in `PUSH_ORDER` is normal (assignment
  syncs *last* in a batch) — the very teacher who just created a
  classroom must be able to immediately add students to it, before
  their own assignment push has landed. Once a `teacher-classrooms`
  record exists for a classroom, it's "claimed" and access narrows to
  its members.
- **The Phase 2 `feedback_result`/`teacher_assessment` split is now
  enforced, not just conventional**: the server rejects a teacher
  pushing to `/feedback-results` and a student pushing to
  `/teacher-assessments` outright (403), which is the authorization
  layer's hard guarantee of "a teacher must not overwrite the
  student-owned half of the shared row" and "a student must not write
  teacher assessment fields."

### Offline behavior

Unchanged from Phase 1/2, now explicitly re-verified under
authentication: `SyncEngine.run_sync()` checks `check_health()`
*before* attempting any login — if the server is unreachable, it
returns `SyncStatus.OFFLINE` immediately, no login is attempted, and
all local reads/writes (including brand-new outbox entries) are
completely unaffected. Login is *only* attempted once the server is
confirmed reachable.

### 401 behavior

A push/pull that returns 401 (`SyncAuthenticationError`) triggers
**one** immediate re-login attempt using the same local credential
(`SyncEngine._reauthenticate()`). If that succeeds, the same
push/pull is retried once and the cycle continues normally. If
re-login also fails (invalid credential, or the server rejects it
again), `run_sync()` returns `SyncStatus.AUTH_REQUIRED` — **the
outbox is never cleared, no local data is touched**, and the next
scheduled sync will try again from scratch. `AUTH_REQUIRED` is
surfaced distinctly in the sidebar/Settings sync status
("● Аутентификация қажет"), separate from `SYNC_ERROR`, so the UI
never claims "server error" for what is actually "please log in
again."

### 403 behavior

A push that returns 403 (`SyncAuthorizationError`) is **never**
retried on the normal 1/5/15/30-minute backoff schedule — it's marked
failed with a 24-hour retry delay instead (`_AUTHORIZATION_DENIED_RETRY_DELAY`
in `sync_engine.py`), since a permission denial will not resolve
itself by retrying quickly. The outbox entry is preserved (not
dropped) so the failure remains visible/debuggable, and other pending
entity types in the same sync cycle continue processing normally.

### Multi-teacher isolation

Each teacher's JWT only ever proves *their own* `sync_id` — every
route re-derives their assigned classrooms from `teacher-classrooms`
live. Teacher A creating/grading records for their own classroom never
touches, and is never visible to, Teacher B, even if both are
authenticated against the same server at the same time (verified in
`tests/integration/test_sync_poc_phase3_multi_client.py` and
`server/tests/test_authorization_isolation.py`). If two teachers are
both assigned to the *same* classroom (§6's example), both see it
normally — isolation is per-classroom-membership, not per-teacher-silo.

### Multi-device behavior

The same teacher/student identity authenticating from a second device
gets a **separate** cached token (`AppPreferences` is per-device,
QSettings is per-machine) but the **same** authorization outcome,
since it's re-derived from the same server-side `sync_id`. Local
SQLite stays fully per-device — Phase 3 does not make SQLite remote in
any way; each device still reads/writes its own file and only
exchanges data through the sync protocol.

### Backward compatibility with Phase 1/2

`SyncEngine.__init__` gained three **optional** parameters
(`get_active_role_and_sync_id`, `get_cached_token`, `set_cached_token`)
— omitted, authentication orchestration is fully disabled and the
engine behaves exactly as it did before Phase 3 (this is how the
existing Phase 1/2 fake-client unit tests keep passing unmodified).
Every real call site (`SyncWorker`, all integration tests, the demo
scripts) now supplies them, since the **server** routes are hard-gated
on `get_current_user()` regardless — an unauthenticated request from
any client, old or new, now gets 401.

## Phase 3 manual demo

`scripts/sync_poc_demo_phase3.py` runs the full §12 scenario against a
real `uvicorn` server on a real socket: Teacher A/8A/Student A and
Teacher B/8B/Student B, Student A submits and syncs (authenticated),
Teacher A pulls/discovers/grades/syncs, Student A pulls the reviewed
result, Teacher B syncs and receives **zero** trace of Student A's
classroom/session/feedback, then the server is stopped/restarted to
prove offline writes still succeed and reconnect+re-authenticate+sync
completes. Prints a PASS/FAIL summary; synthetic data/temp files/an
ephemeral port only.

```bash
python scripts/sync_poc_demo_phase3.py
```

## Phase 4: Raw Arduino Measurement Cloud Sync

Phase 1–3 synced session **metadata** (start/end time, status,
measurement *count*) but never the raw per-sample rows themselves —
see the (now superseded) "Deferred: raw measurements" note in earlier
drafts of this document. Phase 4 closes that gap: the actual
voltage/current/resistance/power samples an Arduino produces during an
experiment are now synced, batched, ordered, and reconstructable on a
second authorized device.

### Data model (local)

No new measurement table — `measurements` (from Phase 1) is unchanged
(`session_id`, `sequence_no`, `timestamp`, `values_json`,
`derived_values_json`, `warnings_json`). Two additive changes:

- `measurement_batches` (new table): `batch_sync_id` (UUID, PK),
  `session_id` (FK → `experiment_sessions.id`), `sequence_start`,
  `sequence_end` (half-open `[start, end)` range over `sequence_no`),
  `sample_count`, `created_at`, `sync_state`, `server_revision`. This
  is the **parent** metadata row that groups a contiguous
  `sequence_no` range into one durable, independently-syncable unit —
  it does not duplicate the measurement rows themselves.
- `idx_measurements_session_sequence_unique`: a `UNIQUE(session_id,
  sequence_no)` index on `measurements`, added defensively (wrapped in
  try/except so pre-existing duplicate rows, if any, only log a
  warning rather than breaking migration). This is what makes a
  duplicate pull/push a safe no-op instead of a duplicate row.

### Why a batch, not one row = one sync unit

`sync_outbox` has `UNIQUE(entity_type, entity_sync_id)` — syncing each
measurement row individually would mean one outbox row and one HTTP
request per sample, which is both architecturally wrong (the outbox is
sized for "durable intents", not a high-frequency sample stream) and
would make an 800-sample experiment issue 800 HTTP requests. A
**batch** (chunk) is the durable sync unit instead: `measurement_batch`
is its own `entity_type` in the outbox, one row per batch, each batch
carrying up to `chunk_size` samples in its wire payload.

### Local → batch → outbox → server flow

```
Arduino → acquisition (live UI/graph, unchanged)
   │
ExperimentWorkspacePage
   │  every sample: session.add_measurement() (in-memory, unchanged)
   │  every 10s (a separate, low-frequency QTimer — NOT per-sample):
   ▼
ISessionRepository.append_measurements()       (incremental INSERT-only)
   │  creates/updates `measurements` rows + an `in_progress`
   │  `experiment_sessions` row if one doesn't exist yet
   ▼
IMeasurementBatchRepository.create_pending_batches_for_session()
   │  chunk_size-sized ranges of NOT-yet-batched sequence_no →
   │  new `measurement_batches` rows, each with a fresh UUID
   ▼
sync_outbox (entity_type="measurement_batch", entity_sync_id=batch_sync_id)
   │
SyncEngine._push_pending()                     (same engine/thread as Phase 1-3)
   │  PUSH_ORDER: ... → session → session_student_link → feedback_result
   │  → teacher_assessment → measurement_batch  (LAST — depends on session)
   ▼
POST /api/v1/sync/measurement-batches
   │
server/app/services/sync_service.py::upsert_measurement_batch()
   ▼
sync_measurement_batches (parent) + sync_measurements (child rows) — SQLite/PostgreSQL
```

At experiment **Stop** (`ExperimentWorkspacePage._finalize_and_persist_session()`),
`save_session()` runs as before (destructive delete+reinsert — safe,
since `sequence_no` assignment is deterministic given the in-memory
measurement list order, so it reproduces identical rows), followed by
one more `create_pending_batches_for_session(..., finalize=True)` call
that captures the final partial "tail" (fewer than `chunk_size`
samples) into its own last batch. No tail sample is ever lost.

### Batch/chunk size

Configurable via `AppPreferences.get/set_measurement_batch_chunk_size()`
(Settings-adjacent, `QSettings`-backed, same pattern as
`sync_request_timeout`). **Default: 250 samples per batch** — chosen as
a conservative middle ground: small enough that a single HTTP payload
stays in the tens-of-KB range even with `derived_values`/`warnings`
included, large enough to avoid excessive per-batch HTTP overhead for
a typical multi-hundred-sample Ohm's-Law-style experiment. Tunable
later without any architecture change — the chunk boundary is a pure
function of `chunk_size` at batch-creation time, not baked into the
schema.

### Ordering & idempotency (HARD requirements)

- **Ordering** never relies on wall-clock timestamps (multiple
  readings can share timestamp resolution) — it is carried entirely by
  the existing integer `sequence_no` column (already present since
  Phase 1), which `append_measurements()` assigns deterministically as
  `MAX(sequence_no) + 1, +2, ...` per session.
- **Idempotency**: `batch_sync_id` is a client-generated UUID, stable
  for the life of that batch. `upsert_measurement_batch()` looks the
  `sync_id` up first — if it already exists, it returns the existing
  record **unchanged** (no re-insert, no revision bump). Uploading the
  same batch once or twenty times (e.g. "server committed, client lost
  the response, retried") produces byte-identical final server state.
  Pulling the same batch twice is equally safe: `apply_remote_batch()`
  writes measurement rows via `INSERT OR IGNORE`, protected by the
  `UNIQUE(session_id, sequence_no)` index.

### Partial session upload / restart safety / offline-first

- Sync can begin **while the experiment is still running** — the
  10-second incremental-persist timer in `ExperimentWorkspacePage`
  calls `append_measurements()` + `create_pending_batches_for_session(
  finalize=False)` throughout acquisition, not only at Stop. Each tick
  is a single `executemany()` (a few ms), decoupled from the 10 Hz
  UI-only elapsed-timer, so it never introduces UI jank or blocks
  Arduino acquisition — this was an explicit risk/complexity trade-off
  (see the module docstring in `experiment_workspace_page.py` next to
  `_INCREMENTAL_PERSIST_TIMER_INTERVAL_MS`).
- Pending batch/outbox state lives in SQLite, never only in RAM — an
  app crash/restart mid-experiment loses nothing already flushed to
  disk (verified by `test_pending_batches_survive_repository_restart`
  and step 6 of the live demo script).
- A server outage never blocks local writes: `SyncEngine.run_sync()`
  checks `check_health()` first and returns `SyncStatus.OFFLINE`
  immediately if the server is unreachable — measurements keep
  accumulating locally, the live graph/results pages keep working
  unchanged, and pending batches simply wait in the outbox for the
  next successful sync (periodic timer or manual retry — same
  mechanism as every other entity type, no second timer system).

### Authorization

Reuses the Phase 3 JWT + `server/app/services/authorization.py`
helpers verbatim — no second auth mechanism. A batch's authorization
is always derived from its `session_sync_id`, never from anything the
client claims about ownership:

- **Push**: only the student role may upload, and only for a session
  they own (`authorization.student_owns_session()` — the same check
  `feedback-results` push already uses). Any other case is a hard 403.
- **Pull**: filtered, not rejected (matching `sessions`/
  `feedback-results`/`teacher-assessments`) via
  `authorization.current_user_can_access_session()` — a student sees
  only their own sessions' batches, a teacher sees only batches
  belonging to sessions of students in their assigned classrooms.

### Server data model

`MeasurementBatchRecord` (`sync_measurement_batches`, PK `sync_id`, FK
`session_sync_id` → `sync_sessions.sync_id`) is the parent;
`MeasurementRecord` (`sync_measurements`) is the child, with a
server-internal-only autoincrement `id` (never exposed to any client —
the batch is still the only externally-visible sync identity) and the
same `UNIQUE(session_sync_id, sequence_no)` invariant as the client
schema. `Teacher → Classroom → Student → ExperimentSession →
MeasurementBatch → Measurements` is the full ownership chain used by
every authorization check.

### API

```
POST /api/v1/sync/measurement-batches   (batch upsert, sync_id-negізді, idempotent)
GET  /api/v1/sync/measurement-batches?updated_since=...&limit=...
```

Extends the existing versioned `/api/v1/sync/*` surface — no parallel
API. Pull supports the same incremental `updated_since` cursor model
as every other entity (safe here specifically because a batch's
`updated_at` is set once, at creation, and never changes — batch
content is immutable).

### Payload limits

`MeasurementBatchPayload.measurements` is Pydantic-bounded to
`1 ≤ len ≤ 5000` — rejects empty batches (malformed-payload protection)
and caps a single HTTP request even if `chunk_size` is later raised
well past its 250-sample default. No additional rate-limiting/streaming
infrastructure was added (§ "avoid premature infra complexity" — a
plain Pydantic bound is sufficient at this scope).

### Compression

`GZipMiddleware` (Starlette, built-in, zero custom code) compresses
outgoing **responses** — the pull/second-device-reconstruction
direction, where a `measurement-batches` payload can be largest.
`httpx` (the client's HTTP layer) already negotiates
`Accept-Encoding: gzip` and decompresses transparently, so this
required no client-side changes. Compressing the **push** (request)
body was deliberately *not* implemented — Starlette's `GZipMiddleware`
only compresses responses, and adding request-body decompression would
require a custom ASGI middleware; push payloads are already small at
the 250-sample default chunk size, so this was judged not worth the
added complexity for a "secondary" (§ spec) concern.

### Legacy measurement handling

`domain/services/sync_migration.py::backfill_measurement_batches()`
(called from `app.py`/`ui/main_window.py`, same idempotent-backfill
convention as `backfill_sync_ids()`/`backfill_session_sync_queue()`)
walks every locally-stored session and calls
`create_pending_batches_for_session(..., finalize=True)` — sessions
saved before Phase 4 existed (via the original `save_session()` path)
already have correctly-assigned `sequence_no` values, so they batch
and sync exactly like new incremental sessions. Idempotent: running it
on every app startup after the first time creates zero new batches.

### Database migration

Purely additive: `CREATE TABLE IF NOT EXISTS measurement_batches`, an
index on `session_id`, and the `UNIQUE(session_id, sequence_no)` index
on the pre-existing `measurements` table (guarded by try/except —
warns instead of crashing if legacy duplicate rows would violate it).
No existing table is altered or dropped; safe to run repeatedly
(verified by calling `initialize_schema()` three times against the
same file with no error).

### Second-device reconstruction (the primary acceptance gate)

Proven end-to-end, not just "rows exist server-side": a two-client
integration test (`tests/integration/test_sync_poc_phase4_measurements.py`)
and a live demo script (`scripts/sync_poc_demo_phase4.py`, against a
real `uvicorn` socket) both have Student A generate and partially sync
33 realistic multi-batch samples (offline gap + restart in between),
then have Teacher A — a **second, fully isolated local SQLite file**,
never touched by Student A's device — pull and call
`session_repository.get_measurements()` on its own database, asserting
exact sample count, order, and numeric values match Student A's
original data.

### A real bug found and fixed during this phase

SQLAlchemy's `DateTime(timezone=True)` does not actually round-trip
timezone-awareness on SQLite (a known SQLite+SQLAlchemy limitation —
PostgreSQL does not have this problem). A pulled measurement's
`timestamp` therefore came back as a naive datetime string; the
client's `Measurement` dataclass rejects naive timestamps, and that
`ValueError` was being silently swallowed inside
`_row_to_measurement()`'s existing "don't let one corrupt row crash the
whole read" guard — meaning **every** pulled measurement row was
silently dropped, with no visible error, until the underlying
reconstruction test/demo caught the resulting all-zero counts. Fixed
by explicitly re-attaching `timezone.utc` when serializing
`MeasurementBatchRecord`/`MeasurementRecord` timestamps in
`server/app/api/sync.py::_isoformat_utc()` before they leave the
server (the wall-clock value itself was always correct — only the
tzinfo marker was lost in the SQLite round trip, so this fix changes
no numeric data). Not a Phase 4 architecture problem, but a latent gap
in the SQLite dev/test backend that Phase 4 was the first phase to
actually exercise this datetime path against.

### Explicit remaining limitations

- Cloud **deletion** of measurements/batches was not implemented —
  auditing the current codebase found no existing local deletion
  behavior for individual measurements/sessions to mirror, so building
  cloud deletion now would be inventing a feature with no local
  counterpart. Deferred until local deletion itself becomes a real
  requirement.
- No teacher-side live/real-time measurement streaming while a student
  experiment is in progress — a teacher only sees a session's data
  after the student's next successful sync. **Superseded by Phase 5**:
  this is no longer "periodic timer (15 min) or manual" — see
  [§Phase 5](#phase-5-connectivity-aware-automatic-sync--near-real-time-classroom-monitoring)
  below for the new ~5–15s automatic delivery path. True sub-second
  real-time streaming (WebSockets) remains an explicit non-goal.
- Push-body gzip compression is not implemented (see Compression
  above).

## Phase 4 manual demo

`scripts/sync_poc_demo_phase4.py` runs the full acceptance scenario
against a real `uvicorn` server on a real socket: Student A generates
25 realistic multi-batch samples, partially syncs while the experiment
is still "running", the server goes down while 8 more samples are
collected offline, the app "restarts" (repositories reopened against
the same SQLite file — proving restart safety), the server returns and
the remaining batches (including the finalized tail) sync with a
verified-idempotent retry, Teacher A (an isolated second client) pulls
and reconstructs all 33 samples with exact order/values, and both an
unassigned Teacher B and an unrelated Student B are confirmed to
receive nothing. Prints a PASS/FAIL summary; synthetic data/temp
files/an ephemeral port only.

```bash
python scripts/sync_poc_demo_phase4.py
```

## Phase 5: Connectivity-Aware Automatic Sync + Near-Real-Time Classroom Monitoring

Phase 1–4 gave every entity (including raw measurement batches) a
correct, idempotent, authorized sync path — but the only things that
actually *triggered* a sync cycle were the "Sync now" button, one call
at app startup, and a 15-minute periodic timer. Internet coming back
after an outage did not, by itself, cause anything to happen sooner
than the next 15-minute tick; a teacher watching a live classroom had
no way to see new data faster than that either. Phase 5 does not
change *what* gets synced or *how* authorization works — it changes
*when* a sync cycle starts.

### Connectivity state model

No new state enum was introduced. `domain/entities/sync_status.py`'s
existing `SyncStatus` (`OFFLINE`/`ONLINE`/`SYNCING`/`SYNCED`/
`SYNC_ERROR`/`AUTH_REQUIRED`) already covered every case Phase 5
needed — the audit found `ONLINE`/`SYNCING` defined but never actually
emitted anywhere. Phase 5 starts emitting `ONLINE`-equivalent UI state
(a cheap connectivity check succeeded, no full cycle needed) where
nothing was shown before; `SYNCING` was already wired to the existing
"● Синхрондалуда..." sidebar text via `sync_started`. Per-record
`SyncState` (`pending_upload`/`synced`/...) is unrelated and untouched
— it describes one row's own sync status, not the app's connectivity.

### `ConnectivityMonitor` (new, pure Python)

`domain/services/connectivity_monitor.py` — no Qt/PySide6 import at
all, matching the existing "`SyncEngine` is pure Python, Qt classes
are thin wrappers" layering (`SyncWorker` is the only thing that ever
constructs one). It holds exactly one piece of state, `last_known_
online: bool | None` (`None` = unknown, e.g. right after app start),
and one method:

```python
result = monitor.check(is_online)
# result.is_online         -- the value just passed in
# result.changed           -- did this differ from the previous check?
# result.just_came_online  -- specifically an OFFLINE-or-unknown -> ONLINE edge
```

`SyncWorker` is the only caller. It never emits UI signals or triggers
a sync from inside `ConnectivityMonitor` itself — the monitor only
answers "did anything change", and the caller decides what to do about
it. This separation is what makes the monitor fully unit-testable
(`tests/unit/test_connectivity_monitor.py`, 9 tests) with zero Qt/
threading/network involved, and is also what caught a real bug during
development (see below).

### `SyncWorker` — two new timers, one coalescing fix

`infrastructure/sync/sync_worker.py` gained two independent `QTimer`s,
each with its own reason to exist at its own frequency:

- **`_connectivity_timer`** (default 12s, `AppPreferences.get_
  connectivity_check_interval_seconds()`) — calls *only*
  `HttpSyncApiClient.check_health()` (one lightweight `GET /health`,
  not a full push/pull cycle) and feeds the result into
  `ConnectivityMonitor.check()`. If that reports `just_came_online`,
  it calls `run_sync_now()` — this is the entire "connectivity-restored
  push trigger" (§4 of the brief). On a *steady* online or offline
  state, this timer costs exactly one cheap health-check request per
  tick and triggers nothing else. It's skipped entirely while a full
  cycle is already running (`_is_syncing`), since a full cycle's own
  outcome already proves connectivity — `_run_sync_cycle()` feeds its
  own result into the same monitor at the end, with sync-triggering
  disabled for that particular call (see "a real bug" below for why
  that distinction matters).
- **`_periodic_timer`** — the *same* eventual-consistency safety net
  Phase 1 always had, now **role-aware**: every tick, it asks "is a
  teacher currently logged in on this device?" (reusing the exact
  `active_teacher_repository`/`active_student_repository` lookup
  `SyncEngine` already used for authentication) and reschedules itself
  with `AppPreferences.get_teacher_auto_refresh_interval_seconds()`
  (default 10s) if so, or the original 15-minute interval otherwise. A
  student's idle-time server load is therefore **unchanged** from
  Phase 1–4 — students get near-real-time delivery through the
  connectivity-restored trigger and the active-experiment trigger
  below instead, never through a shortened periodic timer.

### Sync trigger coalescing (§6 of the brief)

Before Phase 5, `SyncWorker.run_sync_now()` dropped a request outright
if a cycle was already running (`if self._is_syncing: return`). That
under-served the "manual Sync button clicked twice in a row" and
"connectivity-restored trigger fires while the periodic timer is also
mid-cycle" cases: legitimate follow-up requests were silently lost
instead of running once the current cycle finished. `run_sync_now()`
now sets a `_rerun_requested` flag and returns immediately if busy;
`_run_sync_cycle()` runs in a `while` loop (not recursion — no risk of
growing the Python call stack under a burst of triggers) and, after
each cycle, re-loops exactly once more if the flag was set during that
cycle, then stops. Any number of triggers arriving while one cycle
runs coalesce into **at most one** extra cycle — never zero (a
legitimate request is never silently dropped) and never more than one
extra (no "N triggers = N cycles" pile-up, no overlapping cycles).
`get_sync_enabled()` is still honored inside the coalesced re-run, so
a user disabling sync mid-burst stops it immediately rather than after
one more cycle completes.

### Active-experiment near-real-time sync (§5 of the brief)

`ExperimentWorkspacePage` already had (since Phase 4) a 10-second
`_incremental_persist_timer` that flushes newly-acquired measurements
to local SQLite and batches them — entirely local, no network
involvement. Phase 5 adds exactly one more line to that same tick
handler: after a successful local persist, if a `SyncThreadController`
was supplied, call `run_sync_now()` (wrapped in its own `try/except` —
a sync-trigger failure must never be allowed to interrupt acquisition,
matching the existing persist-failure guard right above it).
No second timer was added — the existing Phase 4 timer's interval is
now itself configurable via `AppPreferences.get_active_experiment_
sync_interval_seconds()` (default 10s, same value, now tunable). One
more `run_sync_now()` call was added at the *end* of `_finalize_and_
persist_session()` (the Stop-button/Back/app-quit choke point that
already creates the final `finalize=True` tail batch), so the last
partial batch of a finished experiment delivers immediately rather
than waiting for the next timer tick.

This means, concretely, while a student is actively running an
experiment: every ~10s, if there's newly-batched data, one full
push+pull cycle runs on the sync worker thread — never on the Qt main
thread, never blocking the next Arduino sample from being read.

### Teacher auto-refresh (§8 of the brief)

Two complementary pieces, deliberately kept separate:

1. **Faster server polling** — the role-aware `_periodic_timer`
   above already re-pulls every ~10s (configurable) while a teacher is
   the active local identity, instead of every 15 minutes.
2. **UI refresh on new data** — pulling into the local database isn't
   enough by itself if the teacher is already sitting on, say, the
   Dashboard page and nothing re-queries it. `MainWindow` now tracks
   the currently-visible route (`_on_route_changed`, previously
   discarded) and, in `_on_sync_finished`, if `pulled > 0` **and** the
   current route is one of the data-dependent pages (`dashboard`,
   `results`, `analytics`, `data_journal`, `feedback_teacher`, and the
   student-facing `my_results`/`feedback_student`), calls that page's
   existing `on_enter()` again — every one of those pages already
   defines `on_enter()` as an idempotent `self._refresh()` for normal
   navigation, so this is a direct reuse, not new page-level logic.
   No page polls itself; the choke point is entirely in `MainWindow`.

Polling (not WebSockets) was the deliberate choice here — see
"Compression"-style reasoning in the Phase 4 section for the general
principle; concretely, a classroom-scale FastAPI + SQLite/PostgreSQL
deployment handles a teacher's ~9-GET-requests-per-refresh cycle every
10 seconds without needing persistent connections, a pub/sub layer, or
any new server infrastructure. The repository audit found no existing
push-notification mechanism to build on, and introducing one purely
for this would have meant "rewriting Phase 1–4 architecture" (a stated
non-goal) for a UX improvement that 5–15s polling already delivers.

### Server request/load implications

Approximate steady-state request volume per client, per the mechanisms
above (all reuse the *existing* `/api/v1/sync/*` push+pull cycle — no
new endpoints were added in Phase 5):

| Client state | Requests |
|---|---|
| Idle student (no experiment running, connectivity stable) | 1 health-check GET every 12s; a full 9-pull cycle only every 15 min (unchanged from Phase 1–4) |
| Active student experiment | 1 health-check GET every 12s + one full push+pull cycle (up to ~9 GETs + N batch/session POSTs, N usually 0–1) every ~10s, only while the experiment is running |
| Idle teacher | 1 health-check GET every 12s + one full pull cycle (~9 GETs) every ~10s while logged in |
| Teacher actively monitoring a classroom | same as idle teacher — the pull cadence does not increase further; new data simply appears within one ~10s cycle |

Sync-disabled (`AppPreferences.get_sync_enabled() == False`) still
short-circuits `run_sync_now()` before any HTTP call — Phase 5 did not
touch that gate, and the connectivity timer's health check is the only
request that still fires when sync is otherwise idle (by design: it's
how the app knows to turn sync back on automatically once the server
is reachable again — this ping never pushes or pulls any data itself).

### Restart safety, authorization, retry/backoff, 401/403

All unchanged and reused as-is:

- Pending batches/outbox rows live in SQLite, not RAM — restart safety
  was already proven in Phase 4 and is exercised again here under the
  new interleaved-small-syncs pattern
  (`tests/integration/test_sync_poc_phase5_connectivity.py`).
- Every automatic trigger goes through the exact same `SyncEngine.
  run_sync()` → `_ensure_authenticated()` → push → pull path as manual
  sync always has. A 401 mid-cycle triggers the existing one-shot
  re-login exactly as before; if a device "restarts" (fresh in-memory
  token cache) the next triggered sync transparently logs back in
  using the locally-stored credential, with zero data loss. A 403 is
  never retried more aggressively just because the trigger was
  automatic — the existing 24-hour backoff and "preserve outbox state,
  don't leak the record" behavior apply unchanged.
- Authorization is still 100% server-side (`server/app/services/
  authorization.py`, untouched) — an unassigned teacher or unrelated
  student gets nothing back from *any* of the new automatic triggers,
  exactly as from a manual sync.

### A real bug found and fixed during this phase

The first implementation had `_run_sync_cycle()` feed its own result
into `ConnectivityMonitor` with sync-triggering left *enabled* — which
meant the very first successful cycle after app start (an `unknown ->
True` edge, which `ConnectivityMonitor` correctly treats as "just came
online") would call `run_sync_now()` *from inside itself*, coalescing
into one extra, unnecessary full cycle every single time. Caught by
`tests/unit/test_sync_worker.py::test_run_sync_now_executes_
immediately_when_idle` expecting exactly 1 engine call and observing
2. Fixed by splitting `_update_connectivity_state(is_online,
trigger_sync_on_restore)` — only the lightweight connectivity-timer
path passes `trigger_sync_on_restore=True`; the full-cycle path
updates the monitor's state (so the UI still reflects reality and a
*genuine* later reconnect is still detected) without ever re-triggering
itself.

## Phase 5 manual demo

`scripts/sync_poc_demo_phase5.py` runs the full acceptance scenario
against a real `uvicorn` server on a real socket: Student A and
Teacher A authenticate, Student A generates measurements and the
connectivity monitor's own edge-detection logic (the real
`ConnectivityMonitor` class, exercised exactly as `SyncWorker` uses
it) triggers automatic partial delivery with **no manual Sync call
anywhere in the script**; the server is stopped and Student A keeps
collecting fully offline; the server restarts and the connectivity
monitor detects the edge and auto-uploads the backlog; Student A
finalizes the experiment and the tail batch delivers via the
unconditional finalize trigger; Teacher A's periodic auto-refresh
(also a direct `run_sync()` call, modeling the real periodic-timer
tick) automatically reconstructs all 23 samples with exact order/
values and creates no duplicates on a repeat refresh; an unassigned
Teacher B is confirmed to receive nothing. Prints a PASS/FAIL summary;
synthetic data/temp files/an ephemeral port only.

```bash
python scripts/sync_poc_demo_phase5.py
```

## Phase 5 limitations (explicit, not hidden)

- **~5–15s is a UX target, not a guarantee.** Under real network
  conditions (slow links, server load, a device that's briefly
  suspended) an individual delivery can take longer; there is no
  hard real-time SLA, by design (§ "not hard real-time streaming").
- **The connectivity check is TCP/HTTP-level, not content-aware.** A
  server process that accepts connections but is otherwise wedged
  (e.g. hung on the database) could report healthy without actually
  being able to complete a sync — the subsequent full cycle would then
  surface that as a normal `SYNC_ERROR`, not a connectivity failure.
- **No push notifications.** All delivery is still pull-driven polling
  at the intervals above; a teacher's app must be running and online
  to receive anything, exactly as before Phase 5.
- **Teacher UI refresh is route-scoped, not global.** Only the
  currently-visible data-dependent page re-queries itself; pages not
  currently on screen simply show fresh data the next time the user
  navigates to them (via their own existing `on_enter()`), same as
  always — no background pre-fetching of off-screen pages was added.

## Phase 6: Teacher Live Classroom Monitoring Dashboard

Phase 1–5 made every entity sync correctly and made it sync *fast*
(connectivity-restored triggers, ~10s active-experiment delivery, ~10s
teacher periodic pull) — but there was still no UI that let a teacher
actually *watch* a classroom while it worked. Phase 6 adds exactly
that: a read-model service plus two new pages, built entirely on data
Phase 1–5 already syncs. **No sync protocol changes, no new sync
entity types, no schema changes** — this phase is pure read-model +
UI on top of a stable foundation.

### Architecture decision (audited first, before writing code)

- **Strict data flow, one direction only:** cloud sync → teacher's
  local SQLite (via the existing `SyncEngine.run_sync()` pull path,
  Phase 1–5, untouched) → a new read-model layer
  (`domain/services/teacher_monitoring.py`) → the two new Qt pages.
  The teacher UI **never** queries a student's device or an Arduino
  directly, and never bypasses `SyncEngine` — it only reads rows that
  a prior sync cycle already wrote locally. This mirrors the exact
  layering `ExperimentWorkspacePage` already uses for reading its own
  local data.
- **Entry point:** a new "Сыныпты бақылау" quick-action button on the
  existing `TeacherDashboardPage` (reused, not replaced) opens the new
  `ClassroomMonitoringPage` — no dashboard redesign.
- **No new sync entity, no new tables.** The read model is computed
  on demand from existing `IStudentProgressRepository` +
  `ISessionRepository` + `IClassroomRepository` + `IStudentRepository`
  data — one new interface method was added
  (`ISessionRepository.get_latest_measurement()`, a cheap indexed
  `ORDER BY sequence_no DESC LIMIT 1`, no migration) so the read model
  can find "how fresh is this session" without loading every
  measurement just to check the overview.
- **Aggregation logic lives in `domain/services/teacher_monitoring.py`,
  not in Qt widgets.** Both new pages are thin presentation layers
  that call `compute_classroom_monitoring()` /
  `compute_student_monitoring_detail()` and render the result — no
  business logic inside `ClassroomMonitoringPage` or
  `StudentMonitoringDetailPage` beyond formatting.
- **Auto-refresh reuses the Phase 5 mechanism only.** Both new routes
  were added to `MainWindow._AUTO_REFRESHABLE_ROUTES`; neither page
  polls independently. See "Teacher auto-refresh" in the Phase 5
  section above — unchanged, just extended to two more routes.

### Activity/presence semantics — the honest disclosure (§ required)

Phase 5's delivery mechanism is periodic polling, not a persistent
presence channel. `classify_activity()` in `domain/services/teacher_
monitoring.py` **never claims to know true network presence** — it
only measures "how long since the last measurement synced from this
student arrived":

| State | Meaning | Threshold |
|---|---|---|
| `NOT_STARTED` | student has never linked a session for this experiment | `ProgressStatus.NOT_STARTED` |
| `ACTIVE` | session is running (`ended_at IS NULL`) and the latest synced measurement is recent | age ≤ 15s (`DEFAULT_ACTIVE_WINDOW`) |
| `STALE` ("Дерек күтілуде") | session is running, but no fresh measurement recently — could be a normal pause or a dropped connection, deliberately not distinguished | 15s < age ≤ 60s (`DEFAULT_STALE_WINDOW`) |
| `OFFLINE` | session is running, no measurement for a long time | age > 60s |
| `COMPLETED` | session has `ended_at` set (real finalize, not `ProgressStatus`) | — |

`ACTIVE_WINDOW` (15s) was chosen to tolerate exactly one missed
~10s active-experiment sync tick without flickering to STALE.
`STALE_WINDOW` (60s) requires several consecutive missed ticks before
declaring OFFLINE — a single slow tick is never mistaken for a
disconnect. Both thresholds are named constructor defaults
(`DEFAULT_ACTIVE_WINDOW`/`DEFAULT_STALE_WINDOW`), overridable per call
for tests, never hardcoded inline.

### The bug this design decision prevented

`ProgressStatus.derive_status()` (Phase 2, unchanged) sets
`MEASUREMENT_COMPLETED` the instant `measurement_count > 0` — a
holdover from the old "session saved once, at Stop" model. Under
Phase 4/5's incremental persistence, that condition becomes true
within the first ~10s of *any* running experiment. An early
implementation used `ProgressStatus` directly to gate activity
classification and every actively-running experiment was
misclassified as finished the moment the first batch synced — caught
by 4 failing unit tests before it ever reached the UI. The fix:
`classify_activity()` takes a separate `session_is_running: bool |
None` parameter, derived from `SessionSummary.ended_at is None` (the
one field that is actually authoritative about "is this session still
open"), and never asks `ProgressStatus` that question at all.

### Classroom overview (`ClassroomMonitoringPage`)

A classroom picker (scoped to the current teacher's assigned
classrooms — reuses `TeacherScopedClassroomRepository`, unchanged from
Phase 3), a header (classroom name + student/active/completed/
needs-attention counts from `ClassroomMonitoringSnapshot`'s
properties), a filter combo (Барлығы / Белсенді / Аяқталған / Дерек
күтілуде — the last one matches both STALE and OFFLINE), and a roster
table (name, experiment, status label, measurement count, latest
value, relative last-update time). Rows sort active → stale/offline
("needs attention") → completed → not-started, newest-update-first
within each group (`_sort_key()`); double-clicking an active or
completed row emits `student_selected(student_id, experiment_id)`,
which `MainWindow` routes to `student_monitoring`. Only the *latest*
measurement's values are shown per row (`latest_measurement_values`)
— the overview never loads a student's full measurement history, so
it stays cheap at any classroom size.

### Student detail view (`StudentMonitoringDetailPage`)

Opens `LiveGraphWidget` — the **same widget class**
`ExperimentWorkspacePage` uses live during acquisition, not a second
graphing implementation. Full measurement history is loaded only when
this page is actually opened (`compute_student_monitoring_detail()`
calls `get_measurements()`, the full-history read, unlike the
overview's latest-only read). On the first render for a given session
it calls `set_measurements()` (one full build); subsequent refreshes
call `append_measurement()` for only the new tail
(`detail.measurements[self._appended_measurement_count:]`), never a
full rebuild — `LiveGraphWidget`'s own `sequence_no`-ordered,
dedup-protected append path (unchanged from Phase 4) guarantees no
duplicate points even across repeated no-op refreshes. A session or
experiment change (detected via `session_id != self._shown_session_id`)
is the only thing that triggers a full rebuild. Multi-channel
experiments work generically — channel configuration comes from
`ExperimentDefinition.get_display_channels()`/`graph_y_channels`
exactly as `ExperimentWorkspacePage` already does; nothing here is
hardcoded to one experiment.

### Offline teacher / student-disconnect behavior

- **Teacher offline:** both pages read only local SQLite — they render
  whatever was last pulled, with no modal, no blocking spinner, no
  crash. The connectivity indicator (Phase 5, unchanged) reflects
  reality elsewhere in the UI; these pages simply show data that is,
  by definition, at least as fresh as the last successful pull.
- **Student network loss:** the teacher's last-known measurement count
  and values are retained (never cleared) until either fresh data
  arrives or enough time passes for `classify_activity()` to
  reclassify STALE→OFFLINE. On reconnect, the very next pull cycle
  (periodic ~10s teacher timer or a connectivity-restored trigger)
  delivers the backlog and the UI catches up automatically — no manual
  refresh, no special-cased "resume" code path, because the whole
  system already treats every pull as "get whatever's new since last
  cursor."

### Authorization / isolation

Unchanged, reused: the real boundary is server-side pull filtering
(`server/app/services/authorization.py`, Phase 3). An unassigned
teacher's local SQLite database never receives another teacher's
classroom/student/session/measurement rows in the first place, so
`compute_classroom_monitoring()` for a foreign `classroom_id` returns
`None` — there is no row to aggregate. `ClassroomMonitoringPage` adds
a defense-in-depth check on top: the classroom picker is populated
only from `list_active()` (already teacher-scoped), and
`on_enter(classroom_id=...)` clears any id absent from that list
*before* rendering — verified by
`test_classroom_id_not_in_allowed_list_is_never_shown`, and by the
Phase 6 integration test's unauthorized Teacher C step. A route-level
gate was also added: `classroom_monitoring`/`student_monitoring` are
now explicitly listed in `ui/navigation/navigation_config.py`'s
`_TEACHER_ONLY_DRILLDOWN_ROUTES`, closing a gap where routes absent
from the main navigation table were allowed to every role by default.

### Performance at scale

The overview loads one snapshot per `on_enter()`/auto-refresh tick —
O(students) queries for progress + O(students) single-row "latest
measurement" lookups (indexed, no full measurement scan). Full raw
measurement history is loaded exactly once per detail-page open, for
exactly one student. Verified directly at 30 simulated students in
`tests/unit/test_teacher_monitoring.py::test_thirty_student_classroom_
scale` with no per-student full-history load anywhere in the overview
path.

## Phase 6 manual demo

`scripts/sync_poc_demo_phase6.py` runs the full acceptance scenario
against a real `uvicorn` server on a real socket: Teacher A opens the
classroom dashboard before Student A has started anything (NOT_STARTED
is shown, not a blank error); Student A starts an experiment and the
teacher automatically sees ACTIVE with the correct count; more
measurements stream in and the teacher's detail view grows without any
manual sync call; Student A goes offline mid-experiment and keeps
collecting locally — the teacher retains the last-known count, then
(with `now` advanced past the stale window, no real `sleep`)
reclassifies to OFFLINE; Student A reconnects and the teacher
automatically catches up to the full backlog on the next sync; Student
A finalizes the experiment and the teacher sees COMPLETED with an
exact 33-sample reconstruction and no duplicates on a repeat sync; an
unassigned Teacher C's snapshot for the classroom is confirmed empty.
Prints a PASS/FAIL summary; synthetic data/temp files/an ephemeral
port only.

```bash
python scripts/sync_poc_demo_phase6.py
```

## Phase 6 limitations (explicit, not hidden)

- **Activity state is an inference, not a presence protocol.** As
  documented above, STALE/OFFLINE mean "no fresh data recently," never
  a verified network fact — a student who is actually still connected
  but simply paused between measurements looks identical to one who
  disconnected, until the OFFLINE threshold passes.
- **Still polling-driven, same as Phase 5.** No push notifications were
  added; a teacher's app must be running and online to see anything,
  and delivery latency is bounded by the same ~10s periodic-pull
  cadence Phase 5 established, not improved further here.
- **One "current" experiment per student per classroom view.** If a
  student has progress on multiple experiments, the overview shows
  only the most-recently-started one per `_select_latest_entry()` —
  by design (§ "avoid a second, more complex per-experiment concept"),
  not a limitation planned for near-term fixing.
- **No historical/replay view.** The detail page shows the *current*
  session's data only; reviewing a past, already-completed session's
  full graph from this dashboard was out of scope (existing
  `ResultsPage`/`DataJournalPage` already serve that need).

## Phase 7: Teacher Actions and Session History

Phase 6 gave the teacher a *read-only* live view of the classroom.
Phase 7 turns that into a two-way, pedagogically-scoped workflow:
teachers can send short feedback notes to students from the
monitoring page, students see them without leaving their normal
"Кері байланыс" page, and teachers can drill from "watching this
student right now" into "reviewing what they already did" — closing
the "No historical/replay view" gap the Phase 6 section above
explicitly flagged.

### Architecture decision

The audit surfaced one finding that reshaped the design: Phase 2's
existing `experiment_feedback`/`teacher_assessment` tables are a
**student-submits→teacher-grades** workflow (one row per session, a
single 0-10 score+comment, no free-text ad-hoc note capability, no
delivery/read state). That is a different concept from "teacher sends
a short live note" — reusing it would have overloaded a table that
already has a clear, different meaning. Instead:

1. **A new, small, additive entity: `TeacherNote`** (`domain/entities/
   teacher_note.py`) — one row per note, multiple notes per student
   over time (a feed, matching the brief's mockup), not a single
   graded slot. New table `teacher_notes` via `CREATE TABLE IF NOT
   EXISTS` (zero risk to existing data, the same migration-free
   additive convention `database.py` already uses).
2. **Delivery state reuses the existing `SyncState` column** — shown
   to the teacher as "Жіберілуде"/"Жеткізілді", exactly like `Student`/
   `Classroom` already expose their own sync state. No new vocabulary.
3. **Session history reuses `DataJournalPage`, not a new page.** It
   already renders `LiveGraphWidget` and had no student filter — one
   new optional `on_enter(student_id=None, session_id=None)` parameter
   (backward-compatible, sticky-default matches every other Phase 6
   page) lets `StudentMonitoringDetailPage` deep-link straight into
   one student's history.
4. **Sync wiring follows the exact Phase 4 (`measurement_batch`)
   template** — one new entity type in `PUSH_ORDER`, `SyncEngine`,
   `HttpSyncApiClient`; server model/schema/service/routes; push
   authorization reuses `teacher_can_access_student()` (already
   existed) — no new authorization primitive invented.

### Existing components reused

`SyncEngine`/`SyncWorker`/`HttpSyncApiClient` (Phase 1, extended, not
replaced), `SyncState` (Phase 1), `IActiveTeacherRepository` (Multi-
Teacher Accounts phase, to resolve "who is the current teacher"),
`DataJournalPage` + `LiveGraphWidget` (existing session history/graph
rendering, Phase 17), `StudentFeedbackPage` (existing student-facing
page, extended with a small panel rather than a new route),
`StudentMonitoringDetailPage` (Phase 6, extended with a feedback panel
and a history button), `teacher_can_access_student()` (Phase 3
authorization), `current_user_can_access_session()`-style server pull
filtering pattern (Phase 2-4). No sync engine, connectivity monitor,
background thread, or polling architecture was duplicated.

### Feedback implementation

`TeacherNote`: `id, teacher_id, student_id, classroom_id, message,
created_at, experiment_id?, session_id?, read_at?, sync_state`.
`ITeacherNoteRepository`/`SqliteTeacherNoteRepository` mirror
`IFeedbackRepository`'s shape (`create()` role-gated to `TEACHER`,
`mark_read()` role-gated to `STUDENT`, plus the same `get_*_sync_
payload()`/`apply_remote_*()`/`mark_*_synced()`/`enqueue_*_for_sync()`
quartet every synced entity in this codebase already has). Unlike
`experiment_feedback`'s two-independent-halves-of-one-row design,
`TeacherNote` is single-direction (only the teacher's half is ever
pushed) — `read_at` is deliberately never part of the wire payload
(see "Delivery/read semantics" below).

Teacher UI: `StudentMonitoringDetailPage` gained a compact "Мұғалім
пікірі" panel below the live graph — a message field, "Жіберу" button,
and a scrollable feed of previously-sent notes (newest first, each
showing its delivery state). Student UI: `StudentFeedbackPage` (the
existing "Кері байланыс" page) gained a small "Мұғалім пікірі" list at
the top, above the existing graded-submissions table — no new route,
no new sidebar item, matching "the smallest coherent UI addition."

### Offline feedback behavior

Sending a note while offline behaves exactly like every other write in
this app: `SqliteTeacherNoteRepository.create()` writes the row
locally and enqueues it to the existing `sync_outbox` table — the
*same* durable, restart-safe outbox every other entity (session,
feedback, measurement batch) already uses. No second queue was built.
The next `run_sync()` — whether the connectivity-restored trigger, the
teacher's ~10s periodic timer, or a manual Sync — picks it up and
pushes it; the teacher never has to press anything extra.

### Student delivery behavior

A note is delivered by the *same* pull cycle as every other entity: the
server-side push authorization (`teacher_can_access_student()`) and
pull filtering (student receives only rows where `student_sync_id ==
current_user.sync_id`) are the real security boundary — verified with
explicit server tests (`server/tests/test_sync_teacher_notes.py`) and
an end-to-end integration test, not just UI-level hiding. Delivery
latency is bounded by the same ~5-15s Phase 5 cadence as everything
else; no new polling loop was added.

### Delivery/read semantics (the honest disclosure)

The brief explicitly allows an honest fallback if a full read-receipt
round-trip isn't cleanly supportable without a meaningfully larger
addition, and that is the path taken here:

| State shown | Meaning | Source |
|---|---|---|
| "Жіберілуде" (teacher) | Note written locally, not yet confirmed by the server | `TeacherNote.sync_state == PENDING_UPLOAD` |
| "Жеткізілді" (teacher) | Server has confirmed the push | `TeacherNote.sync_state == SYNCED` |
| bold / not-bold (student) | Whether *this device* has displayed the note yet | `TeacherNote.read_at` — set locally when the student's feed renders, **never synced** |

A true, teacher-visible "read/acknowledged" state would require a
second, independent sync entity type mirroring `experiment_feedback`/
`teacher_assessment`'s two-halves-of-one-row split (the student's
device pushing a read receipt back up, the teacher's device pulling
it down) — a real, buildable addition, but a meaningfully larger one
than a single-direction note. Per the brief's own suggested fallback,
this was deliberately deferred rather than built partially or faked:
the teacher **never** sees a fabricated "read" claim; the student's
own local "жаңа" (bold) vs. already-seen distinction is genuinely
local-only and does not pretend to be anything more.

### Teacher actions (Part B)

`StudentMonitoringDetailPage` gained exactly two new actions, both
pedagogical/application-level, matching the brief's explicit
do-not-list:

1. **Send feedback** — the compact panel described above.
2. **Open session history** — a "Тәжірибе тарихы" button that emits
   `session_history_requested(student_id)`; `MainWindow` routes this
   to `data_journal` with `student_id` pre-filled, landing the teacher
   on that student's filtered session list (existing `DataJournalPage`
   classroom/student combo cascade, unmodified logic — only the entry
   point is new).

No remote-control capability of any kind was added — the teacher UI
never touches a student's Arduino, never starts/stops an experiment
remotely, never sends arbitrary commands. `TeacherNote.message` is a
plain string rendered as plain text; there is no command channel.

### Session-history implementation

`DataJournalPage.on_enter(student_id: str | None = None, session_id:
str | None = None)` — both parameters optional, defaulting to `None`
so the existing sidebar-navigation call path (`on_enter()`, zero args)
is byte-for-byte unchanged, verified by a dedicated regression test.
When `student_id` is given, the page resolves the student's classroom,
sets the classroom/student filter combos to match (triggering the
page's own existing cascade/render logic — no new filtering code), and
falls back safely to the unfiltered "Барлығы" view if the id isn't
found locally (which, thanks to the server-side sync boundary, means
either a genuinely-unknown id or one belonging to a student this
teacher's device never received in the first place — never a
data leak). When `session_id` is also given, the page additionally
calls its own existing `_on_open_clicked(session_id)` to jump straight
into the detail/graph view.

### Historical graph reuse

Unchanged — `DataJournalPage`'s detail view already used
`LiveGraphWidget.set_measurements()` with `capture_mode=False` (all
saved points always shown), preserving exact `sequence_no` order,
timestamps, channels, and values with no downsampling. Phase 7 adds no
new graph code; the only change is a new *entry point* into an
existing, already-correct rendering path.

### Authorization/isolation results

- **Push**: `POST /api/v1/sync/teacher-notes` rejects (403) unless the
  caller is a teacher, is sending as themselves (`teacher_sync_id ==
  current_user.sync_id`), and is assigned to the target student's
  classroom (`teacher_can_access_student()`). Verified by
  `test_teacher_cannot_write_teacher_note`, `test_teacher_cannot_send_
  note_as_another_teacher`, `test_unassigned_teacher_cannot_send_note_
  to_unrelated_student`.
- **Pull**: teachers receive only notes they authored themselves;
  students receive only notes addressed to them. Verified by
  `test_unrelated_student_never_receives_the_note`, `test_unassigned_
  teacher_does_not_see_others_note`.
- **Session history**: the real boundary remains server-side pull
  filtering (Phase 3, unchanged) — an unauthorized teacher's local
  SQLite never contains another teacher's classroom's sessions, so
  `DataJournalPage`'s `student_id` filter can never leak data even if
  navigated to directly with an arbitrary id (verified by
  `test_on_enter_with_unknown_student_id_falls_back_safely`).
- **A real pre-existing gap was found and closed**: the router key
  `"data_journal"` (used by `MainWindow._SIDEBAR_ROUTES["data_log"]`)
  had no matching entry in `NAVIGATION_ITEMS` (only `"data_log"`, the
  *sidebar* key, was present) — so `is_route_allowed_for_role(
  "data_journal", ...)` fell through to the "route not in table =
  allowed to everyone" default, meaning a student could in principle
  have reached this teacher-only page via a direct `navigate()` call.
  No student-visible UI ever exercised this path before Phase 7 (no
  sidebar button), but Phase 7's new `student_id`-based deep link made
  it a live concern, not just a theoretical one. Fixed by adding
  `"data_journal"` to `_TEACHER_ONLY_DRILLDOWN_ROUTES`, the exact
  established Phase 6 mechanism — see "Bugs discovered/fixed" in the
  final report.

### Duplicate-prevention and restart safety

`upsert_teacher_note()` follows the same "immutable once created, if
it already exists just return it" pattern as `upsert_measurement_
batch()` — a `TeacherNote` is never edited after being sent (matching
the pedagogical use case: a sent note stays as sent), so repeated
pushes of the same `sync_id` never produce duplicates or divergent
content server-side, and `apply_remote_note()`'s local `INSERT OR
REPLACE` is equally idempotent on repeated pulls. Restart safety is
inherited for free: the note lives in local SQLite (`teacher_notes`
table) and the pending push lives in the same durable `sync_outbox`
table every other entity already uses — nothing new to lose on
restart.

### Performance considerations

The classroom overview (`ClassroomMonitoringPage`, Phase 6, untouched)
never loads notes or full measurement history for every student — Part
A/B's new panels only query `list_for_student()`/session history when
`StudentMonitoringDetailPage`/`DataJournalPage` are actually opened for
one specific student, matching Phase 6's established "overview shows
summaries only, full detail loads on demand" performance discipline.
No N × full-history queries were introduced.

### Migration/schema decision

One new table (`teacher_notes`), zero modifications to any existing
table, zero data migration needed. Added via `CREATE TABLE IF NOT
EXISTS` in `_SCHEMA_STATEMENTS` (`infrastructure/storage/database.py`)
— the same idempotent, additive convention documented at the top of
that file. No `ALTER TABLE` was required since this is a wholly new
concept, not an extension of an existing row.

### Test coverage

`tests/unit/test_sqlite_teacher_note_repository.py` (repository CRUD,
role gating, idempotent `mark_read()`, sync payload round-trip,
read-state preservation on remote apply), `tests/unit/test_sync_
engine_teacher_notes.py` (push/pull/offline/retry/no-duplicate-
re-enqueue, mirroring the Phase 4 measurement-batch wiring tests),
`tests/unit/test_http_sync_api_client.py` (hyphenated route segment),
`tests/unit/test_navigation_config.py` (the `data_journal` gate fix),
`tests/unit/test_student_monitoring_detail_page.py` and `tests/unit/
test_student_feedback_page.py` (both extended with the new panels),
`tests/unit/test_data_journal_page_phase7.py` (new `student_id`/
`session_id` params, backward compatibility, safe fallback),
`server/tests/test_sync_teacher_notes.py` (push/pull authorization,
idempotency, isolation), and the two-client acceptance integration
test below.

### Live demo

`scripts/sync_poc_demo_phase7.py` runs an 11-check scenario against a
real `uvicorn` server: classroom/student visibility, active-session
detection, a teacher note sent and automatically received by the
student with no manual action, continued measurement updates, an
offline/reconnect cycle, session completion, opening the completed
session's exact history, duplicate-prevention across repeated syncs,
and confirming an unauthorized teacher gets neither history access nor
a successful send (a direct push attempt is rejected with 403) while
an unrelated student receives nothing.

```bash
python scripts/sync_poc_demo_phase7.py
```

## Phase 7 limitations (explicit, not hidden)

- **No synced read-acknowledgement**, as detailed above — the teacher
  sees delivery state (pending/delivered) but never a truthful
  "student has read this" signal. Deferred, not faked.
- **One "current" session per student per experiment in the history
  deep-link path.** `StudentMonitoringDetailPage`'s history button
  filters `DataJournalPage` by student only; if a student has multiple
  historical sessions for different experiments, the teacher sees all
  of them in the existing journal list (this was already how
  `DataJournalPage` worked) and picks the one they want — there is no
  "jump straight to one specific past session" shortcut from the
  monitoring page, only "jump to this student's filtered journal."
- **`DataJournalPage`'s auto-refresh still resets all filters,
  including the new student filter** — this is unchanged, pre-existing
  behavior (`on_enter()` has always reset every filter on every call,
  by design, per its own Phase 17 docstring), now also applying to the
  new `student_id` filter. If a teacher is viewing one student's
  filtered history and a background sync fires while `data_journal` is
  the active route, the filter resets to "Барлығы" like any other
  filter on this page always has. Not a Phase 7 regression — a
  pre-existing page-level convention this phase intentionally did not
  redesign.
- **Notes are plain text only** — no attachments, formatting, or rich
  content, matching "this is teacher feedback, not WhatsApp."
- **No notification/badge outside the existing pages** — a student
  only sees a new note when they navigate to "Кері байланыс"; there is
  no toast, badge count, or interruption of an active experiment.

## Phase 8: Advanced Analytics and Learning Progress

### Architecture decision (audited first, before writing code)

A three-way parallel audit (`AnalyticsPage`/dashboard/results/journal,
the measurement/graph stack, and navigation/feedback/export) found that
**most of the numeric analysis this phase asks for already existed**:
`domain/services/graph_analysis.py` (min/max/avg/std-dev/CV/SEM, linear
regression, trapezoidal energy integral) and `domain/services/
experiment_report_data.py` (per-session per-channel statistics) were
already a complete, reusable, Qt-free stats engine wired into
`LiveGraphWidget` and `ExperimentReportDialog`. U(t)/I(t)/P(t)/U(I) are
not hypothetical additions — they are the real, working configuration
of `current-voltage`/`ohms-law`/`current-work-power` experiments,
already replayed per-session by `DataJournalPage`. The actual gap was
**per-student granularity**: every existing aggregate (`AnalyticsPage`'s
KPIs/charts, `compute_dashboard_counts()`, `ClassroomActivitySnapshot`)
was classroom-wide or experiment-wide, never broken down per individual
student, and no "weak/strong topic" or "alert" concept existed anywhere.
Phase 8 was therefore built as a read-model + UI phase — one new
domain service computing per-student aggregates from data that already
existed, plus UI wiring to surface it and navigate from it — not a new
analysis engine, not a new graph widget, not a new sync entity, and not
a new page.

### New domain layer (zero schema change)

- `domain/entities/learning_analytics.py` — `TopicPerformanceLevel`
  (WEAK/STRONG/NEUTRAL), `TopicPerformance` (per-experiment attempted/
  completed/reviewed counts, average score, completion rate, level),
  `StudentLearningProgress` (per-student rollup: topics tuple, overall
  average, overall completion rate, weakest/strongest topic),
  `AlertKind` (OVERDUE/LOW_SCORE/AWAITING_REVIEW_TOO_LONG), `TeacherAlert`.
  Same "never materialized, always recomputed" convention as
  `StudentMonitoringSnapshot` (Phase 6) — nothing here is a new table.
- `domain/services/learning_analytics.py` — `compute_students_learning_
  progress()` (groups `StudentExperimentProgress` by student, computes
  per-topic scores/levels/weakest/strongest), `compute_teacher_alerts()`
  (three alert kinds from existing progress fields, zero new repository
  dependency), `resolve_channel_value()`/`compute_channel_trend()` (the
  "measurement analytics" thin wrapper — `power` is computed fresh with
  the same `P = U × I` formula `CalculationEngine` already uses for
  experiments where it isn't a stored derived channel, e.g. Ohm's Law).
- `domain/services/analytics_csv_exporter.py` — `AnalyticsCsvExporter.
  export(rows, output_path) -> bool`, same shape/error-swallowing
  convention as `csv_exporter.py`, `utf-8` encoding (matched to
  `region_analysis_exporter.py`, not `utf-8-sig`).

### Score-based topic performance, honestly labeled

Weak/strong topic classification is a threshold on `teacher_score`
(falling back to `level1_percentage` scaled to 0-10 when no teacher
score exists yet) — a **score-based proxy**, never claimed as
concept-level diagnostic. True per-question/concept tagging would
require a new `topic` column on the `questions` table; this was
identified and explicitly deferred, not started (see limitations
below). Laboratory completion statistics follow the same honesty rule
already established by `ClassroomActivitySnapshot`: always "of students
who started this lab, what fraction finished," never a fabricated
"vs. the whole roster" percentage, because the domain has no
"assignment" concept.

### UI changes

- `ui/pages/analytics_page.py` — a new "Оқушылар бойынша үлгерім" panel
  below the four existing classroom/experiment/status/trend panels: a
  table (name, classroom, average score, completion rate, weakest/
  strongest topic color-coded via the existing `COLOR_ERROR`/
  `COLOR_SUCCESS`/`COLOR_TEXT_MUTED` tokens, a "Толығырақ" action per
  row) plus a "CSV экспорт" button. Reuses the page's existing
  classroom/experiment filter results (`records_no_period`) to scope
  the underlying `StudentExperimentProgress` query instead of
  duplicating filter logic. New signal:
  `student_monitoring_requested(student_id, experiment_id)`.
- `ui/pages/teacher_dashboard_page.py` — a new "Ескертулер" panel
  (same empty-state/table pattern as the existing "Соңғы нәтижелер"
  panel) sourced from `compute_teacher_alerts()`, with a "Қарау" action
  per row. Same new signal shape:
  `student_monitoring_requested(student_id, experiment_id)`.
- `ui/main_window.py` — both new signals wired identically to the
  existing `classroom_monitoring_page.student_selected` pattern:
  `router.navigate("student_monitoring", student_id=…,
  experiment_id=…)`. No new destination page — `StudentMonitoringDetail
  Page` (Phase 6/7) already has both the feedback panel and the
  "Тәжірибе тарихы" history button built in, so this single route
  satisfies "navigate from analytics to student monitoring, session
  history, and teacher feedback." Zero new repository construction —
  both pages already received `student_progress_repository`/
  `classroom_repository` from earlier phases.

### A real bug found and fixed during this phase

Manual screenshot verification caught a `QTableWidget` rendering defect
in both new tables: re-invoking `on_enter()` (as `MainWindow` does on
route re-entry and on `sync_finished(pulled>0)` auto-refresh) called
`setCellWidget()` again on cells that already held a per-row action
button. Qt does not guarantee the previous widget is cleaned up in that
case, so a stale button from the first render stayed layered underneath
the freshly redrawn row text, producing a visibly overlapping "Толығырақ"
label on row 0. Fixed by calling `table.clearContents()` immediately
before `table.setRowCount()` in both `AnalyticsPage._update_student_
progress()` and `TeacherDashboardPage._refresh_alerts()`, which properly
tears down old cell widgets before repopulating. A related, smaller
issue — `resizeColumnsToContents()` sizing the action-button column
before the freshly-inserted button's `sizeHint()` was fully settled,
clipping the button label — was fixed by padding that column's width by
24px after the resize call. Neither defect was visible from unit tests
alone (which don't call `on_enter()` twice against a populated table
with the same row count, and don't assert on rendered pixel geometry);
both were only caught by the screenshot-based manual verification step.

### Explicitly deferred / out of scope for this phase

- **True multi-session graph overlay** (plotting a student's several
  attempts at one experiment on a single plot) — `LiveGraphWidget.set_
  measurements()` takes one `ExperimentSession` at a time, and forcing
  multiple sessions through it risked corrupting the existing
  single-session contract. Teachers instead reach each individual
  session's already-working graph via the existing `data_journal`
  route (reachable from `student_monitoring`, per Phase 7).
- **Per-question/concept-level topic tagging** — would need a new
  `topic`/`concept` column on the `questions` table; `Question` has no
  such field today. Flagged, not started.
- **Aggregated PDF/Excel classroom report** — only the CSV gradebook
  export (`AnalyticsCsvExporter`) was committed; all three existing
  exporters (`CSVExporter`/`PDFExporter`/`ExcelExporter`) remain
  hard-scoped to one `ExperimentSession` and were not touched.
- **No new sync entity.** Analytics and alerts are always computed live
  from data that was already synced in earlier phases — nothing about
  them is itself synced, and no new sync-engine/connectivity-monitor/
  background-thread/polling mechanism was introduced.

### Test coverage

`tests/unit/test_learning_analytics.py` (25 tests: channel-value/trend
resolution, weak/strong/neutral classification boundaries, completion-
rate honesty, weakest/strongest identification, deleted-student skip,
multi-student grouping, all three alert kinds with boundary conditions,
custom thresholds), `tests/unit/test_analytics_csv_exporter.py` (7
tests), `tests/unit/test_analytics_page.py` (6 new tests: empty state,
real-data population, row-action signal emission, classroom-filter
scoping, color-token-only check), `tests/unit/test_teacher_dashboard_
page.py` (4 new tests: empty state, real LOW_SCORE alert population,
row-action signal emission, no-fabricated-alert-for-good-score),
`tests/unit/test_main_window.py` (2 new tests: both `student_monitoring_
requested` signals navigate with the correct `student_id`/
`experiment_id` params) — 74 new/extended tests, all passing alongside
the full pre-existing suite (2542 local + 93 server, 0 unexpected
failures, both invocations run separately per the established
import-collision-avoidance pattern).

### Manual verification

Screenshot-based verification (an ad-hoc script seeding real SQLite
repositories, constructing `AnalyticsPage`/`TeacherDashboardPage`
directly, and grabbing rendered pixmaps) confirmed: the per-student
table populates with real names/classrooms/scores, weak/strong topics
render in the correct token colors, the CSV export button enables only
when rows exist, the alerts panel shows a real LOW_SCORE alert with
correct message text and color, and both action buttons ("Толығырақ"/
"Қарау") render without clipping or overlap after the bug fix above.

## Phase 3 security limitations (explicit, not hidden)

Real per-user authentication and server-side authorization **are**
implemented and tested (see above) — but the following are honest,
documented gaps, not silently assumed to be solved:

- **PIN/access-code hashing is unchanged SHA-256, unsalted.** Phase 3
  deliberately reused the existing Phase-1 scheme (§ "do not rewrite
  working Phase 1/2 architecture unnecessarily") rather than
  introducing a second, parallel credential scheme. This is adequate
  for a classroom PIN gate on a trusted network; it is *not*
  bcrypt/argon2-grade password storage. Upgrading to a per-record
  salted hash is a reasonable future hardening item if the server is
  ever exposed beyond a trusted network.
- **`X-API-Key` is still a single shared secret** across every client
  — it is a coarse "is this a legitimate app build" gate, not
  per-device identity. Per-user identity is entirely carried by the
  JWT layered on top.
- **No token revocation.** A stolen/leaked token remains valid until
  its 60-minute expiry — there is no server-side blocklist. Kept
  deliberately small in scope for Phase 3; a revocation list or
  shorter TTL is straightforward to add later without a redesign.
- **TOFU bootstrap trusts the first login for a given `sync_id`.** If
  an attacker could guess/predict a not-yet-registered `sync_id` and
  race a real user's first login, they could claim that identity.
  UUIDs make this impractical to guess, but it is not cryptographically
  prevented.
- **No rate limiting** on `/api/v1/auth/*` — a brute-force PIN/code
  guessing script is not blocked by the server itself today (local PIN
  entry already has no lockout either — unchanged from Phase 1).

None of the above blocks the acceptance scenario in §12 or the hard
requirement that unauthorized cross-teacher/cross-student access is
rejected — they are limitations of a Phase 3 scope that explicitly
excluded building a full production identity provider.

## Phase 9: Production Deployment and Release Readiness

Phase 9 is a packaging/configuration/deployment phase, not a sync
protocol change — the push/pull cycle, entity types, authorization
rules, and offline-first guarantees documented above are all
unchanged. Full details live in `docs/deployment.md`; the two changes
with any bearing on this document:

- **Server startup refuses to boot on Railway/production if
  `APL_JWT_SECRET` / `APL_SYNC_API_KEY` are still the public
  dev placeholders.** Local runs still warn and continue.
- **Teacher/student login lockout is stored in `login_lockouts`** so
  multiple app instances share the 5-failure / 5-minute lock.
- **Students (and teachers with session access) can
  `DELETE /api/v1/sync/measurement-batches/{sync_id}`.** Pull omits
  tombstoned batches.
- **The desktop client's `sync/api_base_url` setting now rejects any
  value that isn't `http://`/`https://`** (`AppPreferences.set_sync_api_base_url()`)
  — a defensive validation, not a new capability; the client already
  supported a configurable, non-localhost, HTTPS-capable server URL
  since Phase 3.

A new `tests/integration/test_phase9_multi_pc_isolation.py` re-verifies
the full offline/sync/authorization contract described throughout this
document, but end-to-end across two/three genuinely separate on-disk
SQLite databases (simulating real separate PCs) rather than the
single-process multi-client pattern used by earlier phase tests.

## Deferred until a later phase (Phase 10+)

Per the Phase 1/2/3/4/5/6/7/8/9 briefs' explicit "do not yet" lists: hard
real-time (sub-second) measurement streaming, WebSockets/push
notifications, cloud file storage, auto-update, production cloud
credentials/deployment, deleting SQLite, mandatory internet login,
internet-dependent student experiments, wholesale repository rewrites,
a full production identity provider (see security limitations above),
email/password accounts, a browser/web frontend, a mobile app, cloud
deletion of measurements/sessions, remote Arduino control, a synced
teacher-visible read-acknowledgement for feedback notes (deferred
honestly, see Phase 7 limitations above), rich/attachment-bearing
feedback, notification badges/toasts, and monitoring more than one
"current" experiment per student at once. Connectivity-restored
push-triggered sync and near-real-time (~5–15s) classroom monitoring
**were built in Phase 5** — see
[§Phase 5](#phase-5-connectivity-aware-automatic-sync--near-real-time-classroom-monitoring)
above. A live teacher classroom monitoring dashboard on top of that
delivery mechanism **was built in Phase 6** — see
[§Phase 6](#phase-6-teacher-live-classroom-monitoring-dashboard) above.
Teacher→student feedback notes and session-history drill-down from
the monitoring workflow **were built in Phase 7** — see
[§Phase 7](#phase-7-teacher-actions-and-session-history) above.
Per-student learning progress, weak/strong topic identification,
teacher dashboard alerts, and CSV gradebook export **were built in
Phase 8** — see
[§Phase 8](#phase-8-advanced-analytics-and-learning-progress) above;
only true multi-session graph overlay, per-question/concept-level topic
tagging, and an aggregated PDF/Excel classroom report remain out of
scope there (see Phase 8's own deferred list). Production Windows
packaging, a per-user runtime data directory, and server production
configuration **were built in Phase 9** — see
[§Phase 9](#phase-9-production-deployment-and-release-readiness) above
and `docs/deployment.md`; only a real installer (MSI/Setup.exe — Inno
Setup was unavailable in the build environment), an actual deployed
Postgres instance, and UI-automation-verified click-through of the
packaged executable remain out of scope there (see Phase 9's own
deferred list in the final report). Across all phases, only true hard
real-time streaming, a persistent presence protocol, and a synced
read-receipt remain out of scope.
