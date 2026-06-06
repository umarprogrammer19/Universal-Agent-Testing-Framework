import asyncio
import os
import ssl
import sys
from logging.config import fileConfig
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config, create_async_engine

from alembic import context

# Make sure the project root is on sys.path so 'from db.models import Base' works
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

load_dotenv()

# Alembic Config object
config = context.config

# Wire up logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import metadata for autogenerate support
from db.models import Base  # noqa: E402
target_metadata = Base.metadata


def _build_async_url_and_ssl(raw_url: str) -> tuple[str, dict]:
    """
    Convert a standard postgresql:// URL to postgresql+asyncpg://, strip
    psycopg2-only query params (sslmode, channel_binding), and return the
    cleaned URL plus a connect_args dict with the correct SSL context.
    """
    parsed = urlparse(raw_url)
    scheme = "postgresql+asyncpg"

    params = parse_qs(parsed.query, keep_blank_values=True)
    sslmode = params.pop("sslmode", ["disable"])[0]
    params.pop("channel_binding", None)   # asyncpg does not support this

    clean_query = urlencode({k: v[0] for k, v in params.items()})
    clean_url = urlunparse(parsed._replace(scheme=scheme, query=clean_query))

    connect_args: dict = {}
    if sslmode in ("require", "verify-ca", "verify-full"):
        ssl_ctx = ssl.create_default_context()
        if sslmode == "require":
            # Trust the server cert without CA verification (equivalent to
            # psycopg2's sslmode=require behaviour on Neon/Supabase)
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
        connect_args["ssl"] = ssl_ctx

    return clean_url, connect_args


_RAW_URL = os.environ["DATABASE_URL"]
_ASYNC_URL, _CONNECT_ARGS = _build_async_url_and_ssl(_RAW_URL)
config.set_main_option("sqlalchemy.url", _ASYNC_URL)


# ---------------------------------------------------------------------------
# Offline mode (generates SQL without a live connection)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Online mode (async)
# ---------------------------------------------------------------------------

def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(
        _ASYNC_URL,
        poolclass=pool.NullPool,
        connect_args=_CONNECT_ARGS,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
