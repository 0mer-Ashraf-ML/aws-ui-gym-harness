"""
Pytest configuration and fixtures for testing
"""
import asyncio
import sys
from pathlib import Path
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.core.database import Base, AsyncSessionLocal, get_db
from app.main import app


# Override database URL for testing - use existing database
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:password@localhost:5432/harness_main_aws"

# Create test engine
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

# Create test session factory
TestingSessionLocal = async_sessionmaker(
    class_=AsyncSession,
    bind=test_engine,
    expire_on_commit=False
)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Create a fresh database session for each test.
    Rolls back all changes on errors to ensure test isolation.
    """
    # Create all tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session
    session = TestingSessionLocal()
    try:
        yield session
        # Test passed - commit changes
        await session.commit()
    except Exception:
        # Test failed or raised exception - rollback all changes
        await session.rollback()
        raise
    finally:
        # Always close the session
        await session.close()
    
    # Drop all tables after test
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def client():
    """Create a test client for FastAPI."""
    return TestClient(app)


@pytest_asyncio.fixture
async def async_client():
    """Create an async test client for FastAPI."""
    from httpx import ASGITransport
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac
    
    if hasattr(app, 'dependency_overrides'):
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def async_client_with_db(db_session: AsyncSession):
    """Create an async test client with database session."""
    from httpx import ASGITransport
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest.fixture
def mock_settings(monkeypatch):
    """Mock application settings for testing."""
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("DEBUG", "True")
    yield settings


@pytest.fixture(autouse=True)
def reset_state():
    """Reset application state before each test."""
    yield
    # Cleanup after test
    if hasattr(app, 'dependency_overrides'):
        app.dependency_overrides.clear()


