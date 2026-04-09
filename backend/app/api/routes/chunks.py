from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from pgvector.sqlalchemy import Vector
from app.db import get_db
from app.models.chunk import Chunk

router = APIRouter()


class ChunkCreate(BaseModel):
    content: str
    chunk_type: str
    start_line: int
    end_line: int
    embedding: list[float]
    file_id: int


class ChunkBatchCreate(BaseModel):
    chunks: list[ChunkCreate]


@router.post("/chunks")
async def create_chunks(body: ChunkBatchCreate, db: AsyncSession = Depends(get_db)):
    now = datetime.utcnow()
    created = []
    for c in body.chunks:
        chunk = Chunk(
            content=c.content,
            chunk_type=c.chunk_type,
            start_line=c.start_line,
            end_line=c.end_line,
            embedding=c.embedding,
            file_id=c.file_id,
            created_at=now,
        )
        db.add(chunk)
        created.append(chunk)
    await db.commit()
    for chunk in created:
        await db.refresh(chunk)
    return {"count": len(created), "ids": [c.id for c in created]}


class SearchRequest(BaseModel):
    embedding: list[float]
    limit: int = 10
    repository_id: int | None = None


@router.post("/chunks/search")
async def search_chunks(body: SearchRequest, db: AsyncSession = Depends(get_db)):
    query = select(Chunk).order_by(
        Chunk.embedding.cosine_distance(body.embedding)
    ).limit(body.limit)

    if body.repository_id is not None:
        from app.models.file import File
        query = query.join(File).where(File.repository_id == body.repository_id)

    result = await db.execute(query)
    chunks = result.scalars().all()
    return [
        {
            "id": c.id,
            "content": c.content,
            "chunk_type": c.chunk_type,
            "start_line": c.start_line,
            "end_line": c.end_line,
            "file_id": c.file_id,
        }
        for c in chunks
    ]
