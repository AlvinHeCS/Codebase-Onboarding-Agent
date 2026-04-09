from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.db import get_db
from app.models.repository import Repository
from app.models.file import File

router = APIRouter()


class RepositoryCreate(BaseModel):
    name: str
    url: str


class FileCreate(BaseModel):
    name: str
    filePath: str
    content: str
    repository_id: int


@router.post("/repositories")
async def create_repository(body: RepositoryCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Repository).where(Repository.url == body.url))
    repo = existing.scalar_one_or_none()
    if repo:
        return {"id": repo.id, "name": repo.name, "exists": True}

    now = datetime.utcnow()
    repo = Repository(
        name=body.name,
        url=body.url,
        created_at=now,
        updated_at=now,
    )
    db.add(repo)
    await db.commit()
    await db.refresh(repo)
    return {"id": repo.id, "name": repo.name, "exists": False}


@router.get("/repositories/{repo_id}")
async def get_repository(repo_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repo = result.scalar_one_or_none()
    if not repo:
        return {"error": "Repository not found"}
    return {"id": repo.id, "name": repo.name, "url": repo.url}


@router.post("/repositories/{repo_id}/files")
async def create_file(repo_id: int, body: FileCreate, db: AsyncSession = Depends(get_db)):
    now = datetime.utcnow()
    file = File(
        name=body.name,
        filePath=body.filePath,
        content=body.content,
        repository_id=repo_id,
        created_at=now,
        updated_at=now,
    )
    db.add(file)
    await db.commit()
    await db.refresh(file)
    return {"id": file.id, "name": file.name}
