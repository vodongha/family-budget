"""SQLAlchemy engine + session, wired to Oracle ADB through python-oracledb thin mode.

Thin mode needs no Oracle Instant Client. mTLS to ADB is established by pointing
oracledb at the unzipped wallet directory (config_dir + wallet_location) and the
wallet password set when the wallet was downloaded. The DSN is a TNS alias from the
wallet's tnsnames.ora (e.g. ``familybudget_tp``).

The engine is created lazily on first use, not at import time. That keeps importing
this module (and the whole app) free of an Oracle driver requirement — tests run
against SQLite without python-oracledb installed, and the real connection is only
opened when a request actually needs the database.
"""

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _connect_args() -> dict[str, str]:
    return {
        "user": settings.oracle_user,
        "password": settings.oracle_password,
        "dsn": settings.oracle_dsn,
        "config_dir": settings.wallet_dir,
        "wallet_location": settings.wallet_dir,
        "wallet_password": settings.wallet_password,
    }


def get_engine() -> Engine:
    """Lazily build the Oracle ADB engine.

    Sync on purpose: FastAPI runs sync routes in a threadpool, which is plenty for
    this workload. Async Oracle is still young — upgrade later only if measured.
    """
    global _engine
    if _engine is None:
        _engine = create_engine(
            "oracle+oracledb://",
            connect_args=_connect_args(),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
        )
    return _engine


def _get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), autoflush=False, expire_on_commit=False
        )
    return _session_factory


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a session and always closes it."""
    session = _get_session_factory()()
    try:
        yield session
    finally:
        session.close()
