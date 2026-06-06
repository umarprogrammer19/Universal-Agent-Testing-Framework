import os
import ssl
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

load_dotenv()

_RAW_URL = os.getenv("DATABASE_URL")
if not _RAW_URL:
    raise EnvironmentError("DATABASE_URL is not set in the environment / .env file.")


def _build_async_url_and_ssl(raw_url: str) -> tuple[str, dict]:
    """Strip psycopg2-only params and build an asyncpg-compatible URL + ssl ctx."""
    parsed = urlparse(raw_url)
    scheme = "postgresql+asyncpg"

    params = parse_qs(parsed.query, keep_blank_values=True)
    sslmode = params.pop("sslmode", ["disable"])[0]
    params.pop("channel_binding", None)

    clean_query = urlencode({k: v[0] for k, v in params.items()})
    clean_url = urlunparse(parsed._replace(scheme=scheme, query=clean_query))

    connect_args: dict = {}
    if sslmode in ("require", "verify-ca", "verify-full"):
        ssl_ctx = ssl.create_default_context()
        if sslmode == "require":
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
        connect_args["ssl"] = ssl_ctx

    return clean_url, connect_args


DATABASE_URL, _CONNECT_ARGS = _build_async_url_and_ssl(_RAW_URL)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    connect_args=_CONNECT_ARGS,
)
_SessionFactory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with _SessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
