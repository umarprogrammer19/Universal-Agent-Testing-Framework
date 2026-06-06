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
    """Convert to psycopg2-compatible URL.
    - Strips channel_binding (not supported by psycopg2)
    - Adds connect_timeout=30 so Neon has time to wake from suspension
    """
    parsed = urlparse(raw_url)

    params = parse_qs(parsed.query, keep_blank_values=True)
    params.pop("channel_binding", None)
    # Give Neon up to 30 s to wake from suspension before failing
    params.setdefault("connect_timeout", ["30"])

    clean_query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(scheme="postgresql", query=clean_query))


DATABASE_URL = _build_sync_url(_RAW_URL)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,       # test connection health before each use
    pool_recycle=300,         # recycle connections every 5 min (Neon suspends at ~5 min idle)
    pool_size=5,
    max_overflow=10,
    connect_args={"connect_timeout": 30},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
