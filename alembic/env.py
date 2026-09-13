import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from alembic import context

# Make sure the app package is importable when alembic is run from the project root.
sys.path.insert(0, os.getcwd())

from app.core.config import settings  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import _build_engine_kwargs  # noqa: E402
import app.models  # noqa: E402,F401  (registers all model classes on Base.metadata)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Override the sqlalchemy.url from alembic.ini with the app's runtime setting,
# so a single DATABASE_URL env var drives both the app and migrations.
_cleaned_url, _connect_args = _build_engine_kwargs(settings.DATABASE_URL)
config.set_main_option("sqlalchemy.url", _cleaned_url)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    # Built directly (not via async_engine_from_config) so the Neon/SSL
    # connect_args resolved above (e.g. `ssl=` context) are actually applied.
    connectable = create_async_engine(_cleaned_url, poolclass=NullPool, connect_args=_connect_args)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

