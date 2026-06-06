import os
import ssl
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

load_dotenv()

_RAW_URL = os.getenv("DATABASE_URL")
if not _RAW_URL:
    raise EnvironmentError("DATABASE_URL is not set in the environment / .env file.")


def _build_sync_url(raw_url: str) -> str:
    """Convert to psycopg2-compatible URL (strip channel_binding, keep sslmode)."""
    parsed = urlparse(raw_url)
    scheme = "postgresql"

    params = parse_qs(parsed.query, keep_blank_values=True)
    params.pop("channel_binding", None)   # not supported by psycopg2

    clean_query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(scheme=scheme, query=clean_query))


DATABASE_URL = _build_sync_url(_RAW_URL)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
