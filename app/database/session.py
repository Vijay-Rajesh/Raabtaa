import ssl
from typing import AsyncGenerator
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


def _build_engine_kwargs(database_url: str) -> tuple[str, dict]:
    """
    Prepare the DB URL + connect_args for asyncpg, handling hosted Postgres
    providers like Neon that require SSL and use connection-string query
    params (sslmode, channel_binding) which asyncpg itself does not accept
    directly -- they must be translated into asyncpg's `ssl=` connect arg
    instead, or asyncpg raises "invalid connection option".
    """
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)

    parts = urlsplit(database_url)

    if not parts.scheme.startswith("postgres"):
        # Non-Postgres URLs (e.g. sqlite for local/dev/test use) are passed
        # through untouched -- the Neon/SSL handling below is Postgres-only,
        # and round-tripping other URLs through urlsplit/urlunsplit can
        # subtly mangle them (e.g. sqlite's triple-slash relative paths).
        return database_url, {}

    query = parse_qs(parts.query)

    sslmode = (query.pop("sslmode", [None])[0] or "").lower()
    query.pop("channel_binding", None)  # accepted by libpq, not by asyncpg

    connect_args: dict = {}
    is_neon = "neon.tech" in (parts.hostname or "")

    if sslmode in ("require", "verify-ca", "verify-full") or is_neon:
        ctx = ssl.create_default_context()
        if sslmode in ("require",) or (is_neon and not sslmode):
            # Neon's own certs are always valid; "require" only mandates
            # encryption, not hostname/CA verification.
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        connect_args["ssl"] = ctx

    new_query = urlencode(query, doseq=True)
    cleaned_url = urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))
    return cleaned_url, connect_args


_database_url, _connect_args = _build_engine_kwargs(settings.DATABASE_URL)

engine = create_async_engine(
    _database_url,
    echo=False,
    future=True,
    pool_pre_ping=True,  # guards against Neon's serverless compute suspending idle connections
    connect_args=_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
