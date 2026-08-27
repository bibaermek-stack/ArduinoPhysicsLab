"""DATABASE_URL нормализациясы — Railway postgres:// схемасы."""

from server.app.db.session import get_database_url


def test_default_is_sqlite_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert get_database_url().startswith("sqlite:///")


def test_railway_postgres_scheme_is_normalized(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgres://user:pass@host:5432/railway",
    )
    assert get_database_url() == "postgresql+psycopg2://user:pass@host:5432/railway"


def test_sqlalchemy_postgresql_scheme_gets_psycopg2_driver(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:pass@host:5432/railway",
    )
    assert get_database_url() == "postgresql+psycopg2://user:pass@host:5432/railway"


def test_public_railway_proxy_gets_sslmode(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgres://user:pass@switchyard.proxy.rlwy.net:12345/railway",
    )
    assert (
        get_database_url()
        == "postgresql+psycopg2://user:pass@switchyard.proxy.rlwy.net:12345/railway?sslmode=require"
    )


def test_internal_railway_host_does_not_force_ssl(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:pass@postgres.railway.internal:5432/railway",
    )
    assert (
        get_database_url()
        == "postgresql+psycopg2://user:pass@postgres.railway.internal:5432/railway"
    )
