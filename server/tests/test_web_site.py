"""Public FastAPI website pages."""


def test_root_health_does_not_need_database(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_download_page_renders(client) -> None:
    response = client.get("/download")
    assert response.status_code == 200
    assert "Windows" in response.text
    assert "/download/windows" in response.text
    assert "ArduinoPhysicsLab.exe" in response.text
    assert "0.10.5" in response.text
    assert "вирус емес" in response.text
    assert "Журнал защиты" in response.text


def test_zip_download_url_is_rewritten_to_exe(monkeypatch) -> None:
    from server.app.web import routes

    monkeypatch.setenv(
        "APL_WINDOWS_DOWNLOAD_URL",
        "https://github.com/bibaermek-stack/ArduinoPhysicsLab/releases/latest/download/ArduinoPhysicsLab.zip",
    )
    assert routes._windows_exe_url().endswith("ArduinoPhysicsLab.exe")


def test_download_windows_offers_exe(client, monkeypatch) -> None:
    from server.app.web import routes

    monkeypatch.setattr(routes, "_local_windows_exe", lambda: None)
    response = client.get("/download/windows", follow_redirects=False)
    assert response.status_code == 303
    assert "no-store" in (response.headers.get("cache-control") or "")
    assert "ArduinoPhysicsLab.exe" in response.headers["location"]


def test_home_page_renders(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Arduino Physics Lab" in response.text
    assert "Тіркелу" in response.text
    assert "Windows қолданбасы" in response.text
    assert "feature-grid" in response.text


def test_register_login_and_choose_role(client) -> None:
    register = client.post(
        "/register",
        data={"email": "web@school.kz", "password": "secret1", "display_name": "Веб"},
        follow_redirects=False,
    )
    assert register.status_code == 303
    assert register.headers["location"] == "/role"
    role = client.post("/role", data={"role": "teacher"}, follow_redirects=False)
    assert role.status_code == 303
    assert role.headers["location"] == "/app"
    app_page = client.get("/app")
    assert app_page.status_code == 200
    assert "T-" in app_page.text


def test_home_forwards_google_oauth_code(client) -> None:
    response = client.get("/?code=abc&state=xyz", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"].startswith("/api/v1/auth/google/callback?")
    assert "code=abc" in response.headers["location"]


def test_google_setup_page_shows_web_client_uri(client) -> None:
    response = client.get("/google-setup")
    assert response.status_code == 200
    assert "Web application" in response.text
    assert "arduinophysicslab-production-ab65.up.railway.app" in response.text
    assert "redirect_uri_mismatch" in response.text


def test_login_required_for_people(client) -> None:
    response = client.get("/people", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_web_student_connects_with_teacher_code(client) -> None:
    from server.tests.conftest import _TEST_API_KEY

    teacher = client.post(
        "/api/v1/auth/register",
        json={"email": "ask@school.kz", "password": "secret1", "display_name": "Асқар Серікұлы"},
        headers={"X-API-Key": _TEST_API_KEY},
    )
    assert teacher.status_code == 200
    teacher_headers = {
        "X-API-Key": _TEST_API_KEY,
        "Authorization": f"Bearer {teacher.json()['access_token']}",
    }
    selected = client.post("/api/v1/auth/select-role", json={"role": "teacher"}, headers=teacher_headers)
    teacher_code = selected.json()["public_id"]

    register = client.post(
        "/register",
        data={"email": "solo-web@school.kz", "password": "secret1", "display_name": "Дербес"},
        follow_redirects=False,
    )
    assert register.status_code == 303
    role = client.post("/role", data={"role": "student"}, follow_redirects=False)
    assert role.status_code == 303
    profile = client.get("/profile")
    assert profile.status_code == 200
    assert "Дербес режим" in profile.text
    assert "Мұғалімге қосылу" in profile.text
    sent = client.post(
        "/profile/connect-teacher",
        data={"teacher_code": teacher_code},
        follow_redirects=False,
    )
    assert sent.status_code == 303
    after = client.get("/profile")
    assert "Қабылдау күтілуде" in after.text
    people = client.get("/people")
    assert "Дербес" in people.text
    assert "Қабылдау" in people.text or "мұғалім/оқушы" in people.text


def test_lab_requires_login(client) -> None:
    response = client.get("/lab", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_monitor_requires_login(client) -> None:
    response = client.get("/monitor", follow_redirects=False)
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


def test_teacher_lab_redirects_to_monitor(client) -> None:
    client.post("/register", data={"email": "lab-t2@school.kz", "password": "secret1", "display_name": "Мұғалім"})
    client.post("/role", data={"role": "teacher"})
    response = client.get("/lab", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/monitor"


def test_student_monitor_redirects_to_lab(client) -> None:
    client.post("/register", data={"email": "lab-s2@school.kz", "password": "secret1", "display_name": "Оқушы"})
    client.post("/role", data={"role": "student"})
    response = client.get("/monitor", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/lab"


def test_live_js_uses_cookie_and_skips_auth_frame(client) -> None:
    js = client.get("/static/live.js")
    assert js.status_code == 200
    assert "LiveLab" in js.text
    assert "/api/v1/live/ws" in js.text
    assert 'location.protocol === "https:" ? "wss:"' in js.text
    assert "type=auth" not in js.text
    assert '"auth"' not in js.text
    assert "'auth'" not in js.text


def test_live_js_hello_does_not_mark_connected(client) -> None:
    js = client.get("/static/live.js").text
    marker = 'type === "hello"'
    hello_at = js.find(marker)
    assert hello_at != -1
    snippet = js[hello_at : hello_at + 160]
    assert "setStatus" not in snippet
    assert "COPY.connected" not in snippet


def test_live_js_buckets_samples_per_account(client) -> None:
    js = client.get("/static/live.js").text
    assert "filterAccountId" in js
    assert "account_id" in js
    assert "MAX_POINTS" in js
    click_at = js.find('querySelectorAll("[data-account-id]")')
    assert click_at != -1
    click_block = js[click_at : click_at + 700]
    assert "resetSeries()" not in click_block
    open_at = js.find("addEventListener(\"open\"")
    assert open_at != -1
    open_block = js[open_at : open_at + 220]
    assert "resetSeries()" in open_block


def test_monitor_student_buttons_use_account_id(client, db_session_factory) -> None:
    from server.app.models.account_models import AccountRecord, RelationshipRequestRecord
    from server.tests.conftest import _TEST_API_KEY

    client.post("/register", data={"email": "mon-t@school.kz", "password": "secret1", "display_name": "Мұғалім"})
    client.post("/role", data={"role": "teacher"})
    db = db_session_factory()
    try:
        teacher = db.query(AccountRecord).filter(AccountRecord.email == "mon-t@school.kz").one()
        teacher_code = teacher.public_id
    finally:
        db.close()

    student = client.post(
        "/api/v1/auth/register",
        json={"email": "mon-s@school.kz", "password": "secret1", "display_name": "Оқушы"},
        headers={"X-API-Key": _TEST_API_KEY},
    )
    assert student.status_code == 200
    student_headers = {
        "X-API-Key": _TEST_API_KEY,
        "Authorization": f"Bearer {student.json()['access_token']}",
    }
    selected = client.post("/api/v1/auth/select-role", json={"role": "student"}, headers=student_headers)
    assert selected.status_code == 200
    student_headers["Authorization"] = f"Bearer {selected.json()['access_token']}"
    sent = client.post(
        "/api/v1/student/connect-teacher",
        json={"teacher_code": teacher_code},
        headers=student_headers,
    )
    assert sent.status_code == 200

    db = db_session_factory()
    try:
        request_row = db.query(RelationshipRequestRecord).one()
        request_id = request_row.id
        student_row = db.query(AccountRecord).filter(AccountRecord.email == "mon-s@school.kz").one()
        student_id = student_row.id
    finally:
        db.close()

    accepted = client.post("/people/accept", data={"request_id": request_id}, follow_redirects=False)
    assert accepted.status_code == 303
    page = client.get("/monitor")
    assert page.status_code == 200
    assert f'data-account-id="{student_id}"' in page.text
    assert "Оқушы" in page.text

