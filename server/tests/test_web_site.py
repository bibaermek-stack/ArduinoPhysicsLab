"""Public FastAPI website pages."""


def test_root_health_does_not_need_database(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_home_page_renders(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Arduino Physics Lab" in response.text
    assert "Тіркелу" in response.text


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


def test_google_setup_page_shows_web_client_uri(client) -> None:
    response = client.get("/google-setup")
    assert response.status_code == 200
    assert "Web application" in response.text
    assert "/api/v1/auth/google/callback" in response.text
    assert "redirect_uri_mismatch" in response.text


def test_login_required_for_people(client) -> None:
    response = client.get("/people", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
