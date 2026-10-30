"""
Database connection, session management, and schema initialization.
Configures SQLite / relational database engine with thread-safe settings.
"""

from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from config.settings import settings, logger

# Create SQLAlchemy engine
is_sqlite = settings.DATABASE_URL.startswith("sqlite")

connect_args = {}
if is_sqlite:
    connect_args = {"check_same_thread": False, "timeout": 30}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    echo=False,
)

# Enable foreign key support for SQLite
if is_sqlite:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Provide a transactional database session scope."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Database session rollback due to error: {e}")
        raise
    finally:
        db.close()


def init_db() -> None:
    """Create all tables and register analytical SQL views."""
    from database.schema import Base
    from database.views import create_views
    logger.info("Initializing database schema...")
    Base.metadata.create_all(bind=engine)
    create_views(engine)
    logger.info("Database schema and views initialized successfully.")
