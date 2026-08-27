"""§26 "Server Health / Version" тесттері."""


def test_health_returns_ok_status(client) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["api_version"] == "v1"
    assert "server_time" in body


def test_health_does_not_require_api_key(client) -> None:
    """§ health-ты бекітпей ашық қалдыру — connectivity check ешбір
    аутентификациясыз жылдам жауап беруі керек."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
