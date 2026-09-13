from app.database.session import _build_engine_kwargs


def test_neon_url_gets_ssl_and_strips_unsupported_params():
    url = (
        "postgresql+asyncpg://neondb_owner:pass123@ep-cool-lab-123456"
        ".us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    )
    cleaned, connect_args = _build_engine_kwargs(url)

    assert "sslmode" not in cleaned
    assert "channel_binding" not in cleaned
    assert cleaned.startswith("postgresql+asyncpg://neondb_owner:pass123@ep-cool-lab-123456")
    assert "ssl" in connect_args


def test_neon_url_without_explicit_sslmode_still_gets_ssl():
    url = "postgresql+asyncpg://user:pass@ep-abc-123.eu-central-1.aws.neon.tech/neondb"
    cleaned, connect_args = _build_engine_kwargs(url)

    assert cleaned == url
    assert "ssl" in connect_args


def test_local_postgres_url_untouched_no_ssl():
    url = "postgresql+asyncpg://postgres:postgres@localhost:5432/Raabta"
    cleaned, connect_args = _build_engine_kwargs(url)

    assert cleaned == url
    assert connect_args == {}


def test_plain_postgres_url_uses_asyncpg_driver():
    url = "postgresql://postgres:postgres@localhost:5432/Raabta"

    cleaned, connect_args = _build_engine_kwargs(url)

    assert cleaned == "postgresql+asyncpg://postgres:postgres@localhost:5432/Raabta"
    assert connect_args == {}


def test_sqlite_url_passed_through_unchanged():
    url = "sqlite+aiosqlite:///./test.db"
    cleaned, connect_args = _build_engine_kwargs(url)

    assert cleaned == url
    assert connect_args == {}


def test_non_neon_postgres_url_with_sslmode_require_still_gets_ssl():
    url = "postgresql+asyncpg://user:pass@some-other-host.example.com:5432/mydb?sslmode=require"
    cleaned, connect_args = _build_engine_kwargs(url)

    assert "sslmode" not in cleaned
    assert "ssl" in connect_args
