from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.routes import health, users, repositories, chunks, code, tools
from sqlalchemy import text
from app.db import engine
from app.models.base import Base
from app.models import Chunk, File, Repository, User  # noqa: ensure all models are registered


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="Codebase Onboarding Agent", lifespan=lifespan)

app.include_router(health.router)
app.include_router(users.router)
app.include_router(repositories.router)
app.include_router(chunks.router)
app.include_router(code.router)
app.include_router(tools.router)
