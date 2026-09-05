# Live Lab Tandem Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Site `/lab` and `/monitor` show the student's live Arduino samples within ~1 s while the Windows `.exe` remains the USB controller and opens from `arduinolab://open`.

**Architecture:** In-memory `LiveHub` fans WebSocket `samples` from one desktop publisher per student account to authorized browsers. Durable `sync_worker` is untouched. Deep link and a single-instance gate live only on Windows desktop.

**Tech Stack:** FastAPI WebSocket, Starlette `TestClient`, Jinja + `static/live.js` (no npm), PySide6 QThread worker, `websockets` client, HKCU protocol registration.

**Spec:** `docs/superpowers/specs/2026-09-04-live-lab-tandem-design.md`

## Global Constraints

- Nested repo root: `ArduinoPhysicsLab-main/` (not the outer Downloads folder).
- Tests: `$env:PYTHONPATH = (Get-Location).Path`; Python `C:\Users\USER\.tools\python\python.exe`.
- Kazakh UI copy only; no new PIN/student-code screens.
- Do not commit `release/*.exe` (~77 MB).
- Do not install lucide or unused libraries; `websockets` is the only new desktop dependency.
- PySide6 stays; no Tkinter.
- Secrets stay out of git; live WS uses existing account JWT / `apl_web_token` cookie.
- Railway stays one replica (in-memory hub).
- START/STOP is not sent from the site in v1; ignore `type=command`.
- GUI thread never opens a WebSocket (same rule as `SyncWorker`).

## File map

| File | Responsibility |
|---|---|
| `server/app/services/live_hub.py` | In-memory publishers, viewers, 120 s buffer, rate limit |
| `server/app/services/people_service.py` | Add `list_linked_students` |
| `server/app/api/live.py` | `/api/v1/live/ws` auth + hub wiring |
| `server/app/main.py` | Include live router |
| `server/app/web/routes.py` | `/lab`, `/monitor` |
| `server/app/web/templates/lab.html` | Student live page |
| `server/app/web/templates/monitor.html` | Teacher live page |
| `server/app/web/static/live.js` | Canvas plot + WS client |
| `server/app/web/templates/base.html` | Nav links |
| `server/app/web/templates/dashboard.html` | Lab/monitor buttons |
| `infrastructure/sync/live_stream_worker.py` | QThread WS publisher |
| `infrastructure/sync/live_stream_controller.py` | UI-thread facade |
| `infrastructure/os/protocol_handler.py` | `arduinolab://` HKCU |
| `infrastructure/os/single_instance.py` | QLocalServer gate |
| `requirements.txt` | `websockets` |
| `build/app.spec` | hiddenimport `websockets` |
| `app.py` / `main.py` / `ui/main_window.py` / `ui/pages/experiment_workspace_page.py` | Wire worker, deep link, measurements |

---

### Task 1: In-memory LiveHub

**Files:**
- Create: `server/app/services/live_hub.py`
- Test: `server/tests/test_live_hub.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `SendFn = Callable[[dict], None]`
  - `class LiveHub`
  - `LiveHub.__init__(self, *, max_buffer_seconds: float = 120.0, max_points_per_sec: float = 20.0) -> None`
  - `LiveHub.reset(self) -> None`
  - `LiveHub.set_publisher(self, account_id: str, send: SendFn | None) -> SendFn | None`
  - `LiveHub.add_viewer(self, viewer_id: str, watch_ids: frozenset[str], send: SendFn) -> None`
  - `LiveHub.remove_viewer(self, viewer_id: str) -> None`
  - `LiveHub.publish_samples(self, account_id: str, *, experiment_id: str, session_id: str, points: list[dict]) -> int`
  - `LiveHub.publish_status(self, account_id: str, *, state: str, experiment_id: str = "") -> None`
  - `LiveHub.buffer_for(self, account_id: str) -> list[dict]`
  - `LiveHub.publisher_state(self, account_id: str) -> str`  # `offline` \| `idle` \| `measuring`

- [ ] **Step 1: Write failing tests**

Create `server/tests/test_live_hub.py`:

```python
from server.app.services.live_hub import LiveHub


def test_samples_reach_only_watchers() -> None:
    hub = LiveHub()
    mine: list[dict] = []
    other: list[dict] = []
    hub.add_viewer("v1", frozenset({"stu-1"}), mine.append)
    hub.add_viewer("v2", frozenset({"stu-2"}), other.append)
    accepted = hub.publish_samples(
        "stu-1",
        experiment_id="ohms-law",
        session_id="s1",
        points=[{"t": "2026-09-04T12:00:00Z", "values": {"voltage": 1.2}}],
    )
    assert accepted == 1
    assert len(mine) == 1
    assert mine[0]["type"] == "samples"
    assert mine[0]["account_id"] == "stu-1"
    assert other == []


def test_teacher_does_not_see_unwatched_student() -> None:
    hub = LiveHub()
    seen: list[dict] = []
    hub.add_viewer("teacher", frozenset({"linked-stu"}), seen.append)
    hub.publish_samples(
        "independent-stu",
        experiment_id="ohms-law",
        session_id="s1",
        points=[{"t": "2026-09-04T12:00:00Z", "values": {"voltage": 3.0}}],
    )
    assert seen == []


def test_late_viewer_gets_buffer() -> None:
    hub = LiveHub(max_buffer_seconds=120)
    hub.publish_samples(
        "stu-1",
        experiment_id="ohms-law",
        session_id="s1",
        points=[{"t": "2026-09-04T12:00:00Z", "values": {"voltage": 1.0}}],
    )
    replayed: list[dict] = []
    hub.add_viewer("late", frozenset({"stu-1"}), replayed.append)
    for frame in hub.buffer_for("stu-1"):
        replayed.append(frame)
    assert any(item.get("type") == "samples" for item in replayed)


def test_rate_limit_drops_excess_points() -> None:
    hub = LiveHub(max_points_per_sec=2)
    hub.publish_samples(
        "stu-1",
        experiment_id="ohms-law",
        session_id="s1",
        points=[{"t": f"2026-09-04T12:00:00.{i:03d}Z", "values": {"voltage": i}} for i in range(10)],
    )
    # First call may accept up to 2; the rest of this burst is dropped.
    accepted = hub.publish_samples(
        "stu-1",
        experiment_id="ohms-law",
        session_id="s1",
        points=[{"t": "2026-09-04T12:00:01Z", "values": {"voltage": 9}}],
    )
    assert accepted == 0


def test_new_publisher_replaces_old_send() -> None:
    hub = LiveHub()
    old: list[dict] = []
    new: list[dict] = []
    previous = hub.set_publisher("stu-1", old.append)
    assert previous is None
    previous = hub.set_publisher("stu-1", new.append)
    assert previous is old.append
```

- [ ] **Step 2: Run tests — expect import failure**

```
python -m pytest server/tests/test_live_hub.py -q
```

Expected: `ModuleNotFoundError: live_hub` or collection error.

- [ ] **Step 3: Implement `LiveHub`**

`server/app/services/live_hub.py`:

- Keep publishers as `dict[str, SendFn]`.
- Viewers as `dict[str, tuple[frozenset[str], SendFn]]`.
- Buffer: `dict[str, deque[tuple[float, dict]]]` keyed by account_id; drop frames older than `max_buffer_seconds` using `time.monotonic()`.
- Rate: `dict[str, tuple[float, int]]` window of 1.0 s; `publish_samples` slices `points[:remaining]` (max 50), returns accepted count.
- Fan-out a frame `{"type":"samples","account_id":account_id,"experiment_id":...,"session_id":...,"points":...}` to every viewer whose `watch_ids` contains `account_id`.
- `publish_status` stores state and fans `{"type":"presence","account_id":...,"state":...,"experiment_id":...}`.
- `publisher_state` is `offline` if no publisher send callback, else last status or `idle`.
- `set_publisher(..., None)` clears publisher and emits presence `offline` to watchers.
- Never log frame bodies.

- [ ] **Step 4: Re-run tests — expect PASS**

```
python -m pytest server/tests/test_live_hub.py -q
```

- [ ] **Step 5: Commit**

```
git add server/app/services/live_hub.py server/tests/test_live_hub.py
git commit -m "Add in-memory live measurement hub"
```

---

### Task 2: Linked students for teacher watch list

**Files:**
- Modify: `server/app/services/people_service.py` (after `student_link_status`)
- Test: `server/tests/test_accounts_people.py`

**Interfaces:**
- Consumes: `KIND_TEACHER_STUDENT`, `RelationshipLinkRecord`, `AccountRecord`
- Produces: `list_linked_students(db: Session, teacher: AccountRecord) -> list[AccountRecord]`

- [ ] **Step 1: Write failing test at the end of `server/tests/test_accounts_people.py`**

```python
def test_list_linked_students_only_accepted(client, db_session_factory) -> None:
    from server.app.models.account_models import AccountRecord
    from server.app.services.people_service import list_linked_students

    teacher_headers, teacher = _auth(client, "link-t@school.kz", "secret1", "Мұғалім", "teacher")
    student_headers, student = _auth(client, "link-s@school.kz", "secret1", "Оқушы", "student")
    lone_headers, _lone = _auth(client, "link-solo@school.kz", "secret1", "Дербес", "student")
    del lone_headers
    sent = client.post(
        "/api/v1/student/connect-teacher",
        json={"teacher_code": teacher["public_id"]},
        headers=student_headers,
    )
    assert sent.status_code == 200
    incoming = client.get("/api/v1/requests/incoming", headers=teacher_headers)
    request_id = incoming.json()["items"][0]["id"]
    client.post(f"/api/v1/requests/{request_id}/accept", headers=teacher_headers)
    db = db_session_factory()
    try:
        teacher_row = db.query(AccountRecord).filter(AccountRecord.email == "link-t@school.kz").one()
        linked = list_linked_students(db, teacher_row)
        assert [row.email for row in linked] == ["link-s@school.kz"]
    finally:
        db.close()
```

- [ ] **Step 2: Run — expect `ImportError` or `NameError` for `list_linked_students`**

```
python -m pytest server/tests/test_accounts_people.py::test_list_linked_students_only_accepted -q
```

- [ ] **Step 3: Implement**

In `people_service.py`:

```python
def list_linked_students(db: Session, teacher: AccountRecord) -> list[AccountRecord]:
    if teacher.role != "teacher":
        return []
    links = (
        db.query(RelationshipLinkRecord)
        .filter(RelationshipLinkRecord.kind == KIND_TEACHER_STUDENT)
        .filter(
            or_(
                RelationshipLinkRecord.account_a_id == teacher.id,
                RelationshipLinkRecord.account_b_id == teacher.id,
            )
        )
        .all()
    )
    result: list[AccountRecord] = []
    for link in links:
        other_id = link.account_b_id if link.account_a_id == teacher.id else link.account_a_id
        other = db.get(AccountRecord, other_id)
        if other is not None and other.role == "student":
            result.append(other)
    result.sort(key=lambda row: (row.display_name or "", row.public_id or ""))
    return result
```

- [ ] **Step 4: Re-run — PASS**

- [ ] **Step 5: Commit**

```
git add server/app/services/people_service.py server/tests/test_accounts_people.py
git commit -m "List accepted students for a teacher live watch set"
```

---

### Task 3: WebSocket `/api/v1/live/ws`

**Files:**
- Create: `server/app/api/live.py`
- Modify: `server/app/main.py` (add `from server.app.api import live` and `app.include_router(live.router, prefix="/api/v1")` next to `people.router`)
- Test: `server/tests/test_live_ws.py`

**Interfaces:**
- Consumes: `LiveHub`, `list_linked_students`, `AccountRecord`, JWT cookie `apl_web_token`, auth frame `{type, token, api_key}`
- Produces: `router = APIRouter(tags=["live"])` with `@router.websocket("/live/ws")`; process-global `hub = LiveHub()` (tests may replace `live.hub`)

Close codes: `4401` bad/missing auth, `4403` no role.

Watch set:
- student viewer / desktop publisher: `frozenset({account.id})`
- teacher viewer: `frozenset(row.id for row in list_linked_students(db, account))`
- desktop teacher: still publisher of `account.id` (no samples expected); allowed

- [ ] **Step 1: Write failing WS tests**

`server/tests/test_live_ws.py` — reuse `_auth` from `test_accounts_people` (copy the helper into this file to avoid import cycles):

```python
from server.tests.conftest import _TEST_API_KEY
from server.tests.test_accounts_people import _auth


def test_ws_rejects_missing_auth(client) -> None:
    try:
        with client.websocket_connect("/api/v1/live/ws") as ws:
            ws.send_json({"type": "ping"})
            ws.receive_json()
        raise AssertionError("expected close")
    except Exception as exc:
        assert "4401" in str(exc) or "1008" in str(exc) or "401" in str(exc) or exc.__class__.__name__ == "WebSocketDisconnect"


def test_desktop_samples_reach_student_cookie_viewer(client) -> None:
    student_headers, student = _auth(client, "live-s@school.kz", "secret1", "Оқушы", "student")
    token = student_headers["Authorization"].split(" ", 1)[1]
    client.cookies.set("apl_web_token", token)
    with client.websocket_connect("/api/v1/live/ws") as viewer:
        hello = viewer.receive_json()
        assert hello["type"] == "hello"
        assert hello["role"] == "student"
        with client.websocket_connect("/api/v1/live/ws") as desktop:
            desktop.send_json({"type": "auth", "token": token, "api_key": _TEST_API_KEY})
            desk_hello = desktop.receive_json()
            assert desk_hello["type"] == "hello"
            desktop.send_json({
                "type": "samples",
                "experiment_id": "ohms-law",
                "session_id": "sess-1",
                "points": [{"t": "2026-09-04T12:00:00Z", "values": {"voltage": 1.5}}],
            })
        frame = viewer.receive_json()
        while frame.get("type") == "presence":
            frame = viewer.receive_json()
        assert frame["type"] == "samples"
        assert frame["points"][0]["values"]["voltage"] == 1.5


def test_other_student_does_not_receive_samples(client) -> None:
    a_headers, _a = _auth(client, "live-a@school.kz", "secret1", "A", "student")
    b_headers, _b = _auth(client, "live-b@school.kz", "secret1", "B", "student")
    token_a = a_headers["Authorization"].split(" ", 1)[1]
    token_b = b_headers["Authorization"].split(" ", 1)[1]
    client.cookies.set("apl_web_token", token_b)
    with client.websocket_connect("/api/v1/live/ws") as viewer_b:
        viewer_b.receive_json()  # hello
        with client.websocket_connect("/api/v1/live/ws") as desktop_a:
            desktop_a.send_json({"type": "auth", "token": token_a, "api_key": _TEST_API_KEY})
            desktop_a.receive_json()
            desktop_a.send_json({
                "type": "samples",
                "experiment_id": "ohms-law",
                "session_id": "sess-1",
                "points": [{"t": "2026-09-04T12:00:00Z", "values": {"voltage": 9.9}}],
            })
        viewer_b.send_json({"type": "ping"})
        pong = viewer_b.receive_json()
        assert pong["type"] == "pong"
```

If Starlette raises `WebSocketDisconnect` with `.code`, assert `exc.code == 4401`.

- [ ] **Step 2: Run — expect 404 (route missing)**

```
python -m pytest server/tests/test_live_ws.py -q
```

- [ ] **Step 3: Implement `live.py`**

Pattern:

```python
router = APIRouter(tags=["live"])
hub = LiveHub()

def _account_from_token(db, token: str) -> AccountRecord | None:
    # jwt.decode like get_web_account; require payload typ account / acc claim

@router.websocket("/live/ws")
async def live_ws(websocket: WebSocket, db: Session = Depends(get_db)) -> None:
    await websocket.accept()
    cookie = websocket.cookies.get("apl_web_token")
    account = _account_from_token(db, cookie) if cookie else None
    if account is None:
        raw = await websocket.receive_json()
        if raw.get("type") != "auth" or not raw.get("token"):
            await websocket.close(code=4401)
            return
        from server.app.api.deps import get_configured_api_key
        if raw.get("api_key") != get_configured_api_key():
            await websocket.close(code=4401)
            return
        account = _account_from_token(db, str(raw["token"]))
        kind = "desktop"
    else:
        kind = "viewer"
    if account is None or not account.role:
        await websocket.close(code=4403)
        return
    send = lambda frame: asyncio.create_task(websocket.send_json(frame))
    # If event-loop safety is needed, use:
    # loop = asyncio.get_running_loop()
    # send = lambda frame: loop.call_soon_threadsafe(asyncio.create_task, websocket.send_json(frame))
    watch = frozenset({account.id})
    if kind == "viewer" and account.role == "teacher":
        watch = frozenset(row.id for row in list_linked_students(db, account))
    if kind == "desktop":
        old = hub.set_publisher(account.id, send)
        if old is not None:
            pass  # previous desktop is replaced; do not close from hub
    else:
        hub.add_viewer(account.id + ":view", watch, send)
        for student_id in watch:
            for frame in hub.buffer_for(student_id):
                await websocket.send_json(frame)
    await websocket.send_json({"type": "hello", "role": account.role})
    try:
        while True:
            message = await websocket.receive_json()
            mtype = message.get("type")
            if mtype == "ping":
                await websocket.send_json({"type": "pong"})
            elif mtype == "samples" and kind == "desktop":
                points = message.get("points") or []
                if not isinstance(points, list):
                    continue
                hub.publish_samples(
                    account.id,
                    experiment_id=str(message.get("experiment_id") or ""),
                    session_id=str(message.get("session_id") or ""),
                    points=points[:50],
                )
            elif mtype == "status" and kind == "desktop":
                hub.publish_status(
                    account.id,
                    state=str(message.get("state") or "idle"),
                    experiment_id=str(message.get("experiment_id") or ""),
                )
            elif mtype == "command":
                continue
    finally:
        if kind == "desktop":
            current = hub.set_publisher(account.id, None)  # only clear if still this send
        else:
            hub.remove_viewer(account.id + ":view")
```

Fix publisher teardown: `set_publisher` should only clear if `send` still matches this connection (compare function identity). Add `LiveHub.clear_publisher_if(account_id, send)` if needed and a unit test in `test_live_hub.py`.

Ignore `type=command`.

- [ ] **Step 4: Include router in `main.py`**

```python
from server.app.api import accounts, auth, health, live, people, sync
...
app.include_router(live.router, prefix="/api/v1")
```

- [ ] **Step 5: Tests PASS**

```
python -m pytest server/tests/test_live_ws.py server/tests/test_live_hub.py -q
```

Also run `server/tests/test_accounts_people.py -q` to confirm no hub import leak.

- [ ] **Step 6: Commit**

```
git add server/app/api/live.py server/app/main.py server/tests/test_live_ws.py server/app/services/live_hub.py server/tests/test_live_hub.py
git commit -m "Expose live measurement WebSocket at /api/v1/live/ws"
```

---

### Task 4: Website `/lab` and `/monitor`

**Files:**
- Create: `server/app/web/templates/lab.html`
- Create: `server/app/web/templates/monitor.html`
- Create: `server/app/web/static/live.js`
- Modify: `server/app/web/routes.py` (add GET `/lab` and GET `/monitor` after `/app`)
- Modify: `server/app/web/templates/base.html` nav (logged-in links)
- Modify: `server/app/web/templates/dashboard.html` actions
- Test: `server/tests/test_web_site.py`

**Interfaces:**
- Consumes: `get_web_account`, `list_linked_students`, cookie session
- Produces: HTML pages that load `/static/live.js` and connect to `ws` derived from `location` (`wss:` if https)

- [ ] **Step 1: Write failing page tests in `test_web_site.py`**

```python
def test_lab_requires_login(client) -> None:
    response = client.get("/lab", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_student_lab_page_has_deep_link(client) -> None:
    client.post("/register", data={"email": "lab-s@school.kz", "password": "secret1", "display_name": "Оқушы"})
    client.post("/role", data={"role": "student"})
    page = client.get("/lab")
    assert page.status_code == 200
    assert "arduinolab://open" in page.text
    assert "/static/live.js" in page.text


def test_teacher_monitor_page_renders(client) -> None:
    client.post("/register", data={"email": "lab-t@school.kz", "password": "secret1", "display_name": "Мұғалім"})
    client.post("/role", data={"role": "teacher"})
    page = client.get("/monitor")
    assert page.status_code == 200
    assert "live.js" in page.text
```

- [ ] **Step 2: Run — expect 404 for `/lab`**

- [ ] **Step 3: Routes**

```python
@router.get("/lab", response_class=HTMLResponse, response_model=None)
def lab_page(request: Request, db: Session = Depends(get_db), account: AccountRecord | None = Depends(get_web_account)) -> Response:
    if account is None:
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)
    if account.role != "student":
        return RedirectResponse("/monitor" if account.role == "teacher" else "/app", status_code=HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request, "lab.html", {"account": account})

@router.get("/monitor", response_class=HTMLResponse, response_model=None)
def monitor_page(request: Request, db: Session = Depends(get_db), account: AccountRecord | None = Depends(get_web_account)) -> Response:
    if account is None:
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)
    if account.role != "teacher":
        return RedirectResponse("/lab" if account.role == "student" else "/app", status_code=HTTP_303_SEE_OTHER)
    students = list_linked_students(db, account)
    return templates.TemplateResponse(request, "monitor.html", {"account": account, "students": students})
```

Import `list_linked_students` in `routes.py`.

- [ ] **Step 4: Templates**

`lab.html`: extends `base.html`; kicker «Зертхана»; status `#live-status`; canvas `#live-chart` width/height 100%; `<a class="btn btn-lab" href="arduinolab://open">Зертхананы бастау</a>`; `<a class="btn btn-ghost" href="/download">.exe жүктеу</a>`; `<script src="/static/live.js"></script>` and `LiveLab.connect({role:"student"})`.

`monitor.html`: student buttons `data-account-id="{{ person.id }}"`; same canvas; `LiveLab.connect({role:"teacher"})`.

Kazakh copy: «Қолданбаны ашыңыз», «Қосылған», «Өлшеу жүріп жатыр», «Офлайн».

- [ ] **Step 5: `static/live.js`**

Implement `window.LiveLab = { connect(opts) { ... } }`:

- `proto = location.protocol === "https:" ? "wss:" : "ws:"`
- `url = proto + "//" + location.host + "/api/v1/live/ws"`
- Cookie auth is automatic (same origin).
- On `hello` / `presence` / `samples`, update `#live-status` and draw canvas.
- Chart: keep last 300 points per series key in `values`; y auto-scale; x is index; teal stroke `rgb(0,137,123)`.
- Reconnect after 1 s on close (not 4401/4403).
- Teacher: clicking `[data-account-id]` sets `filterAccountId` and ignores other `samples.account_id`.

No npm. No eval.

- [ ] **Step 6: Nav + dashboard**

`base.html` logged-in: add `<a href="/lab">` if student and `/monitor` if teacher — simplest: always show both labels «Зертхана» → `/lab` for students and `/monitor` for teachers using `{% if account.role == 'teacher' %}`.

`dashboard.html` actions: student `href="/lab"` «Зертхана»; teacher `href="/monitor"` «Бақылау».

- [ ] **Step 7: Tests PASS**

```
python -m pytest server/tests/test_web_site.py -q
```

- [ ] **Step 8: Commit**

```
git add server/app/web/routes.py server/app/web/templates/lab.html server/app/web/templates/monitor.html server/app/web/static/live.js server/app/web/templates/base.html server/app/web/templates/dashboard.html server/tests/test_web_site.py
git commit -m "Add student lab and teacher monitor live pages"
```

---

### Task 5: Desktop `LiveStreamWorker` (no GUI socket)

**Files:**
- Create: `infrastructure/sync/live_stream_worker.py`
- Create: `infrastructure/sync/live_stream_controller.py`
- Modify: `requirements.txt` (add `websockets==15.0.1` or current stable pin after `pip index` — if unset, pin `websockets==14.2`)
- Test: `tests/unit/test_live_stream_worker.py`

**Interfaces:**
- Consumes: `AppPreferences.get_account_token()`, `get_sync_api_base_url()`, `domain.services.sync_auth.get_configured_sync_api_key()`, `domain.entities.measurement.Measurement`
- Produces:
  - `class LiveStreamWorker(QObject)` with slots `initialize`, `shutdown`, `enqueue_measurement(measurement: Measurement, session_id: str)`, `set_status(state: str, experiment_id: str)`
  - `class LiveStreamController(QObject)` mirroring `SyncThreadController`: `start()`, `stop()`, `enqueue_measurement(...)`, `set_status(...)`
  - WS URL: `http`→`ws`, `https`→`wss`, path `/api/v1/live/ws`
  - Flush every 500 ms; ping/status idle every 5 s; reconnect delays `[1, 2, 5, 10]` seconds capped at 10
  - First message: `{"type":"auth","token": token, "api_key": key}`

Worker must accept an injected `connect` callable for tests:

```python
def __init__(self, preferences: AppPreferences, connect_ws=None) -> None:
    self._connect_ws = connect_ws  # async (url) -> fake with send/recv/close
```

- [ ] **Step 1: Failing unit tests** (no real network)

```python
from datetime import datetime, timezone
from domain.entities.measurement import Measurement
from infrastructure.storage.app_preferences import AppPreferences
from infrastructure.sync.live_stream_worker import LiveStreamWorker, ws_url_from_http


def test_ws_url_from_http() -> None:
    assert ws_url_from_http("https://example.com") == "wss://example.com/api/v1/live/ws"
    assert ws_url_from_http("http://127.0.0.1:8000/") == "ws://127.0.0.1:8000/api/v1/live/ws"


Because the worker uses a QThread + asyncio loop, keep the testable core **sync/pure**. Extract:

```python
def build_samples_frame(experiment_id: str, session_id: str, measurements: list[Measurement]) -> dict:
def ws_url_from_http(base: str) -> str:
```

Test those without starting threads. Then a thin test that `enqueue` + `_drain_queue` produces one frame with `values` from `Measurement.all_values()`.

```python
def test_build_samples_frame_uses_all_values() -> None:
    m = Measurement(
        timestamp=datetime(2026, 9, 4, 12, tzinfo=timezone.utc),
        values={"voltage": 1.2},
        experiment_id="ohms-law",
        derived_values={"current": 0.01},
    )
    frame = build_samples_frame("ohms-law", "sess", [m])
    assert frame["type"] == "samples"
    assert frame["points"][0]["values"]["voltage"] == 1.2
    assert frame["points"][0]["values"]["current"] == 0.01
```

- [ ] **Step 2: Run — FAIL missing module**

- [ ] **Step 3: Implement worker + controller**

`live_stream_worker.py`:
- Queue of measurements (thread-safe `queue.Queue`)
- `initialize`: start `QTimer` 500 ms → `flush` slot; start asyncio loop in this thread (`asyncio.new_event_loop()`), connect using `websockets.connect` when token non-empty
- Never call `websockets` from constructor
- `enqueue_measurement`: `put_nowait`, drop if queue > 500
- USB/UI must not wait: `enqueue` is non-blocking
- Do not log token or points

`live_stream_controller.py`: copy `SyncThreadController` structure (`moveToThread`, queued connections, `stop()` waits 3000 ms).

- [ ] **Step 4: Add `websockets==14.2` to `requirements.txt`** (desktop). Server already has `uvicorn[standard]`.

- [ ] **Step 5: Tests PASS**

```
python -m pytest tests/unit/test_live_stream_worker.py -q
```

- [ ] **Step 6: Commit**

```
git add infrastructure/sync/live_stream_worker.py infrastructure/sync/live_stream_controller.py tests/unit/test_live_stream_worker.py requirements.txt
git commit -m "Add desktop live WebSocket publisher worker"
```

---

### Task 6: Wire measurements and session into the worker

**Files:**
- Modify: `app.py` `build_main_window` / `run` to construct `LiveStreamController` when account token exists, `start()` after window shown, `stop()` on logout/`aboutToQuit`
- Modify: `ui/main_window.py` optional `live_stream_controller` argument (default `None` so existing tests stay network-free)
- Modify: `ui/pages/experiment_workspace_page.py` — connect `measurement_ready` to a new optional callback/signal already on the page: add `live_sample_ready = Signal(object, str)` `(Measurement, session_id)` and emit from `_on_measurement_ready_for_device_panel`
- Test: `tests/unit/test_main_window.py`

**Interfaces:**
- Consumes: `LiveStreamController.enqueue_measurement`, `Measurement`, `experiment_controller.session.id`
- Produces: every local sample also queued for live WS; the measurement path does not wait on the socket

- [ ] **Step 1: Failing test in `tests/unit/test_main_window.py`**

```python
from datetime import datetime, timezone
from domain.entities.measurement import Measurement


class DummyLive:
    def __init__(self) -> None:
        self.items: list = []
        self.status: list = []

    def enqueue_measurement(self, measurement, session_id: str) -> None:
        self.items.append((measurement, session_id))

    def set_status(self, state: str, experiment_id: str) -> None:
        self.status.append((state, experiment_id))


def test_live_measurement_slot_queues_sample() -> None:
    dummy = DummyLive()
    window, _home, _list, _workspace = _make_window()
    window.live_stream_controller = dummy
    sample = Measurement(
        timestamp=datetime(2026, 9, 4, 12, tzinfo=timezone.utc),
        values={"voltage": 1.2},
        experiment_id="ohms-law",
    )
    window._on_live_measurement(sample)
    assert dummy.items[0][0] is sample
    assert dummy.status[-1] == ("measuring", "ohms-law")
```

MainWindow slot:

```python
def _on_live_measurement(self, measurement: Measurement) -> None:
    if self.live_stream_controller is None:
        return
    session_id = ""
    controller = getattr(self._experiment_workspace_page, "_experiment_controller", None)
    session = getattr(controller, "session", None)
    if session is not None:
        session_id = str(getattr(session, "id", "") or "")
    self.live_stream_controller.enqueue_measurement(measurement, session_id)
    self.live_stream_controller.set_status("measuring", measurement.experiment_id)
```

- [ ] **Step 2: FAIL — `live_stream_controller` unexpected kwarg**

- [ ] **Step 3: Implement wiring**

- `MainWindow.__init__(..., live_stream_controller=None)`
- Connect both coordinator and single-device `measurement_ready` already go to `_on_measurement_ready_for_device_panel`; at the end of that method call `_emit_live_sample(measurement)`.
- On experiment stop / workspace leave: `set_status("idle", "")` if controller present.
- `app.py`: create controller, `window.live_stream_controller.start()` after `showMaximized` only if `app_preferences.get_account_token()`; `aboutToQuit.connect(controller.stop)`; logout path stops it.

- [ ] **Step 4: Tests PASS** — targeted unit + `tests/unit/test_main_window.py::test_starts_on_home_page_for_student_role` still passes (no live controller).

- [ ] **Step 5: Commit**

```
git add app.py ui/main_window.py ui/pages/experiment_workspace_page.py tests/unit/test_main_window.py
git commit -m "Queue live samples from the experiment workspace"
```

---

### Task 7: `arduinolab://` protocol and single instance

**Files:**
- Create: `infrastructure/os/protocol_handler.py`
- Create: `infrastructure/os/single_instance.py`
- Modify: `app.py` `run()` after `QApplication` exists
- Modify: `main.py` only if argv must be parsed before `run()` — prefer `app.py` reading `sys.argv`
- Test: `tests/unit/test_protocol_handler.py`, `tests/unit/test_single_instance.py`

**Interfaces:**
- Consumes: `sys.executable` / `sys.argv[0]` for frozen exe path
- Produces:
  - `PROTOCOL_SCHEME = "arduinolab"`
  - `register_protocol(exe_path: str, *, set_value=None) -> None`
  - `is_open_url(arg: str) -> bool`  # `arduinolab://open` with optional trailing `/`
  - `class SingleInstance: try_lock() -> bool; send_raise(); on_raise(callback); close()`

- [ ] **Step 1: Failing tests**

```python
from infrastructure.os.protocol_handler import is_open_url, register_protocol, command_for

def test_is_open_url() -> None:
    assert is_open_url("arduinolab://open")
    assert is_open_url("arduinolab://open/")
    assert not is_open_url("http://example.com")

def test_register_protocol_writes_hkcu_shape() -> None:
    written: dict[str, str] = {}
    def fake_set(scheme: str, command: str) -> None:
        written["scheme"] = scheme
        written["command"] = command
    register_protocol(r"C:\Apps\ArduinoPhysicsLab.exe", set_value=fake_set)
    assert written["scheme"] == "arduinolab"
    assert written["command"].endswith('"%1"')
    assert "ArduinoPhysicsLab.exe" in written["command"]
```

Single instance without Qt display if possible: inject a fake server.

```python
def test_second_lock_fails(monkeypatch) -> None:
    from infrastructure.os.single_instance import SingleInstance
    a = SingleInstance(name="apl-test-lock")
    b = SingleInstance(name="apl-test-lock")
    assert a.try_lock() is True
    assert b.try_lock() is False
    a.close()
```

If `QLocalServer` needs `QApplication`, use the module-scoped `qt_application` fixture from other unit tests.

- [ ] **Step 2: FAIL**

- [ ] **Step 3: Implement**

Windows `register_protocol` default `set_value` uses `winreg`:

```python
import winreg
key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\arduinolab")
winreg.SetValueEx(key, None, 0, winreg.REG_SZ, "URL:Arduino Physics Lab")
winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
cmd = winreg.CreateKey(key, r"shell\open\command")
winreg.SetValueEx(cmd, None, 0, winreg.REG_SZ, f"\"{exe_path}\" \"%1\"")
```

Non-Windows `set_value` default: no-op.

`app.py` `run()`:
1. Create `QApplication`
2. `gate = SingleInstance("ArduinoPhysicsLab")`
3. If not `gate.try_lock()`: `gate.send_raise()`; return 0
4. `register_protocol(str(Path(sys.argv[0]).resolve()))` when frozen or always with `sys.executable` fallback for dev (`python main.py` should register `"python" "main.py" "%1"` only if useful; spec says exe path — **register only when `getattr(sys, "frozen", False)`** so dev pytest does not write HKCU)
5. `gate.on_raise(lambda: existing_window.showMaximized())` — store window holder like `main_window_holder`

- [ ] **Step 4: Tests PASS** (protocol tests never touch real registry because they pass `set_value`)

```
python -m pytest tests/unit/test_protocol_handler.py tests/unit/test_single_instance.py -q
```

- [ ] **Step 5: Commit**

```
git add infrastructure/os/protocol_handler.py infrastructure/os/single_instance.py tests/unit/test_protocol_handler.py tests/unit/test_single_instance.py app.py
git commit -m "Register the Arduino Lab URL protocol and keep a single app instance"
```

The protocol scheme string in code is `arduinolab`.

---

### Task 8: Packager, CSS, regression

**Files:**
- Modify: `build/app.spec` `_HIDDEN_IMPORTS` add `"websockets"`
- Modify: `server/app/web/static/app.css` (canvas full width, min-height 280px, `#live-status` muted)
- Modify: `docs/architecture.md` one short subsection pointing at the spec
- Test: existing `server/tests` + `tests/unit/test_role_selection_page.py::test_student_button_emits_login_succeeded_without_code_form`

- [ ] **Step 1: Hiddenimport + CSS**

```python
_HIDDEN_IMPORTS = [
    ...
    "websockets",
]
```

CSS:

```css
#live-chart { width: 100%; min-height: 280px; background: var(--lab-soft); border-radius: var(--radius-sm); }
#live-status { color: var(--muted); }
```

- [ ] **Step 2: Architecture note** (5 lines under «Екі бөлек өнім»): live WS is not journal sync; link the spec path.

- [ ] **Step 3: Regression**

```
python -m pytest server/tests/test_live_hub.py server/tests/test_live_ws.py server/tests/test_web_site.py server/tests/test_accounts_people.py tests/unit/test_live_stream_worker.py tests/unit/test_protocol_handler.py tests/unit/test_role_selection_page.py::test_student_button_emits_login_succeeded_without_code_form -q
```

Expected: all PASS. Do not run the full 2000-test Qt suite in one process (heap abort). Isolated files only.

- [ ] **Step 4: Commit**

```
git add build/app.spec server/app/web/static/app.css docs/architecture.md
git commit -m "Pack live WebSocket client and document the tandem path"
```

Do **not** bump desktop version or publish `.exe` in this plan unless the user asks after the feature works locally.

---

## Spec coverage

| Spec section | Task |
|---|---|
| WebSocket transport, frames, ping | 1, 3, 5 |
| Cookie vs desktop auth, 4401/4403 | 3 |
| Student own stream / teacher accepted only | 1, 2, 3, 4 |
| `/lab` `/monitor`, no START/STOP | 4 |
| Deep link `arduinolab://open` | 4, 7 |
| LiveStreamWorker QThread, 0.5 s flush, backoff | 5, 6 |
| Measurement path does not wait on WS | 5, 6 |
| Single instance | 7 |
| sync_worker unchanged | 6 (new controller beside it) |
| No PIN | 8 regression |
| Buffer 120 s, 20 Hz cap, 50 points | 1 |
| Ignore `command` | 3 |
| One Railway replica / in-memory | 1 (no Redis) |
| PyInstaller hiddenimport | 8 |

## Execution notes

- Work in `ArduinoPhysicsLab-main/`.
- After Task 3 you can manually `uvicorn server.app.main:app --port 8000` and connect two browser sessions.
- Desktop live stream needs a logged-in account token in QSettings pointing at that server.
- Do not treat Defender SmartScreen as a blocker for deep link; download page already explains Allow.
