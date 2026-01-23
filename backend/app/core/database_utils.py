"""
Database utility functions for proper connection management in Celery tasks.
Uses connection pooling to efficiently handle concurrent tasks.
"""
import logging
import threading
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

# Thread-safe singleton pattern for engine and session factory
_engine_lock = threading.Lock()
_engine = None
_session_factory = None


def _get_engine():
    """
    Get or create the shared database engine with proper connection pooling.
    Uses thread-safe singleton pattern to ensure only one engine exists.
    """
    global _engine, _session_factory
    
    if _engine is None:
        with _engine_lock:
            # Double-check pattern
            if _engine is None:
                # Calculate pool size based on worker concurrency
                # Allow for 50 concurrent tasks + some overhead
                pool_size = max(settings.CELERY_WORKER_CONCURRENCY, 50)
                max_overflow = pool_size  # Allow overflow for bursts
                
                # Convert async URL to sync URL for psycopg2
                database_url = settings.DATABASE_URL
                # Remove asyncpg driver if present
                if "postgresql+asyncpg://" in database_url:
                    database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
                # Add psycopg2 driver if not already present
                if database_url.startswith("postgresql://"):
                    database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
                
                # Create engine with connection pooling
                _engine = create_engine(
                    database_url,
                    pool_size=pool_size,
                    max_overflow=max_overflow,
                    pool_timeout=30,  # Wait up to 30s for connection
                    pool_recycle=3600,  # Recycle connections every hour
                    pool_pre_ping=True,  # Verify connections before use
                    connect_args={
                        "connect_timeout": 10,
                        "options": "-c statement_timeout=7200000"  # 2 hours (matches Celery timeout)
                    },
                    echo=settings.DEBUG,
                )
                
                # Create session factory
                _session_factory = sessionmaker(
                    autocommit=False,
                    autoflush=False,
                    bind=_engine,
                    expire_on_commit=False
                )
                
                logger.info(
                    f"✅ Created shared database engine with pool_size={pool_size}, "
                    f"max_overflow={max_overflow}"
                )
    
    return _engine


def _get_session_factory():
    """Get or create the shared session factory."""
    _get_engine()  # Ensure engine is created
    return _session_factory


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions in Celery tasks.
    Uses connection pooling to efficiently handle concurrent tasks.
    Ensures session is properly closed even if errors occur.
    
    Usage:
        with get_db_session() as db:
            # Use db
            pass
    """
    SessionLocal = _get_session_factory()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database session error: {e}", exc_info=True)
        raise
    finally:
        # Always close the session (returns connection to pool)
        try:
            session.close()
        except Exception as e:
            logger.error(f"Error closing session: {e}", exc_info=True)


def dispose_engine():
    """
    Dispose of the shared engine.
    Should only be called during application shutdown or testing.
    """
    global _engine, _session_factory
    
    with _engine_lock:
        if _engine is not None:
            try:
                _engine.dispose()
                logger.info("✅ Disposed shared database engine")
            except Exception as e:
                logger.error(f"Error disposing engine: {e}")
            finally:
                _engine = None
                _session_factory = None
