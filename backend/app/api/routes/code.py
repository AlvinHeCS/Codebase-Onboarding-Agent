import uuid
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from openai import OpenAI
from temporalio.client import Client

from app.config import settings
from app.db import get_db
from app.models.chunk import Chunk
from app.models.file import File

router = APIRouter()


class IngestRequest(BaseModel):
    repo_url: str


class SearchRequest(BaseModel):
    query: str
    limit: int = 10
    repository_id: int | None = None


@router.post("/code")
async def ingest_repo(body: IngestRequest):
    client = await Client.connect(settings.temporal_host)
    handle = await client.start_workflow(
        "IngestRepoWorkflow",
        body.repo_url,
        id=f"ingest-repo-{uuid.uuid4()}",
        task_queue="my-task-queue",
    )
    return {"workflow_id": handle.id, "status": "started"}


@router.post("/search")
async def search_code(body: SearchRequest, db: AsyncSession = Depends(get_db)):
    openai_client = OpenAI(api_key=settings.openai_api_key)
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=[body.query],
    )
    query_embedding = response.data[0].embedding

    query = select(Chunk).order_by(
        Chunk.embedding.cosine_distance(query_embedding)
    ).limit(body.limit)

    if body.repository_id is not None:
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
