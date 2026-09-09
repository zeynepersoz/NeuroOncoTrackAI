"""
NeuroOncoTrack-AI — Test Configuration & Fixtures

Configures environment overrides, SQLite compilation rules for PG-specific types,
async session fixtures, and mock Redis client for isolated testing.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import TypeDecorator, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.ext.compiler import compiles

# Ensure backend directory is on sys.path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# ── SQLite Compatibility Compilation Rules ───────────────────

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(ARRAY, "sqlite")
def compile_array_sqlite(type_, compiler, **kw):
    return "JSON"


# ── Environment Overrides ────────────────────────────────────

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"
os.environ["JWT_PRIVATE_KEY_PATH"] = str(backend_dir / "test_keys" / "private.pem")
os.environ["JWT_PUBLIC_KEY_PATH"] = str(backend_dir / "test_keys" / "public.pem")
os.environ["MFA_ENCRYPTION_KEY"] = "9mSyw-W-4IAo2eHUUecJihAvInSQLW_4-fxqCd3XLYI="


from app.db.base import Base
from app.models.organization import Organization
from app.models.user import User


# ── Database Fixtures ────────────────────────────────────────

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def db_session():
    """Provides an isolated in-memory SQLite async database session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    from sqlalchemy import event
    import sqlite3

    @event.listens_for(engine.sync_engine, "connect")
    def register_sqlite_adapters(dbapi_connection, connection_record):
        # Register python list adapter for SQLite in tests
        sqlite3.register_adapter(list, json.dumps)
        sqlite3.register_adapter(dict, json.dumps)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session

    await engine.dispose()


# ── Mock Redis Fixture ──────────────────────────────────────

class FakeRedis:
    """In-memory Redis client mock for testing rate limiting and blacklisting."""

    def __init__(self):
        self.data: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def set(self, name: str, value: str, ex: int | None = None) -> bool:
        self.data[name] = str(value)
        if ex is not None:
            self.ttls[name] = ex
        return True

    async def setex(self, name: str, time: int, value: str) -> bool:
        self.data[name] = value
        self.ttls[name] = time
        return True

    async def get(self, name: str) -> str | None:
        return self.data.get(name)

    async def exists(self, *names: str) -> int:
        return sum(1 for name in names if name in self.data)

    async def delete(self, *names: str) -> int:
        count = 0
        for name in names:
            if name in self.data:
                del self.data[name]
                count += 1
        return count

    async def incr(self, name: str) -> int:
        val = int(self.data.get(name, 0)) + 1
        self.data[name] = str(val)
        return val

    async def ttl(self, name: str) -> int:
        return self.ttls.get(name, -1)

    async def expire(self, name: str, time: int) -> bool:
        if name in self.data:
            self.ttls[name] = time
            return True
        return False

    def pipeline(self):
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, redis: FakeRedis):
        self.redis = redis
        self.commands = []

    def incr(self, name: str):
        self.commands.append(("incr", name))
        return self

    def ttl(self, name: str):
        self.commands.append(("ttl", name))
        return self

    async def execute(self):
        results = []
        for cmd, arg in self.commands:
            if cmd == "incr":
                res = await self.redis.incr(arg)
            elif cmd == "ttl":
                res = await self.redis.ttl(arg)
            results.append(res)
        return results


@pytest.fixture
def mock_redis():
    return FakeRedis()
