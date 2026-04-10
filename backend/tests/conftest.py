import os
import pytest
from contextlib import asynccontextmanager
from datetime import datetime
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.models.base import Base
from app.models.repository import Repository
from app.models.file import File
from app.models.chunk import Chunk
from app.db import get_db

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/onboarding_agent_test",
)

_seeded = False


async def _seed(engine, session_factory):
    global _seeded
    if _seeded:
        return
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        now = datetime.now()

        repo = Repository(name="test-repo", url="https://github.com/test/repo", created_at=now, updated_at=now)
        session.add(repo)
        await session.flush()

        file1 = File(
            name="main.py",
            filePath="src/main.py",
            content="import os\nimport sys\n\ndef hello():\n    print('hello')\n\ndef goodbye():\n    print('goodbye')\n",
            created_at=now,
            updated_at=now,
            repository_id=repo.id,
        )
        file2 = File(
            name="utils.py",
            filePath="src/utils.py",
            content="class Helper:\n    def run(self):\n        pass\n\ndef hello():\n    return 'hi'\n",
            created_at=now,
            updated_at=now,
            repository_id=repo.id,
        )
        file3 = File(
            name="index.ts",
            filePath="src/index.ts",
            content="function greet(name: string) {\n    return `Hello ${name}`;\n}\n",
            created_at=now,
            updated_at=now,
            repository_id=repo.id,
        )
        session.add_all([file1, file2, file3])
        await session.flush()

        chunks = [
            Chunk(content="import os\nimport sys", chunk_type="import", name=None, start_line=1, end_line=2, file_id=file1.id, created_at=now),
            Chunk(content="def hello():\n    print('hello')", chunk_type="function", name="hello", start_line=4, end_line=5, file_id=file1.id, created_at=now),
            Chunk(content="def goodbye():\n    print('goodbye')", chunk_type="function", name="goodbye", start_line=7, end_line=8, file_id=file1.id, created_at=now),
            Chunk(content="class Helper:\n    def run(self):\n        pass", chunk_type="class", name="Helper", start_line=1, end_line=3, file_id=file2.id, created_at=now),
            Chunk(content="def hello():\n    return 'hi'", chunk_type="function", name="hello", start_line=5, end_line=6, file_id=file2.id, created_at=now),
            Chunk(content="function greet(name: string) {\n    return `Hello ${name}`;\n}", chunk_type="function", name="greet", start_line=1, end_line=3, file_id=file3.id, created_at=now),
        ]
        session.add_all(chunks)
        await session.commit()

    _seeded = True


def _create_test_app():
    """Create a fresh FastAPI app with a no-op lifespan to avoid production DB connections."""
    from fastapi import FastAPI
    from app.api.routes import health, users, repositories, chunks, code, tools

    @asynccontextmanager
    async def test_lifespan(app):
        yield

    test_app = FastAPI(title="Codebase Onboarding Agent", lifespan=test_lifespan)
    test_app.include_router(health.router)
    test_app.include_router(users.router)
    test_app.include_router(repositories.router)
    test_app.include_router(chunks.router)
    test_app.include_router(code.router)
    test_app.include_router(tools.router)
    return test_app


@pytest.fixture()
async def client():
    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    await _seed(engine, session_factory)

    test_app = _create_test_app()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    test_app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    await engine.dispose()
