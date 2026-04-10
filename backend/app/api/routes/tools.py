import re
from fnmatch import fnmatch
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from openai import OpenAI
from app.config import settings
from app.db import get_db
from app.models.file import File
from app.models.chunk import Chunk
from app.models.repository import Repository

router = APIRouter(prefix="/tools")


async def get_repo_id(repo_url: str, db: AsyncSession) -> int:
    result = await db.execute(select(Repository.id).where(Repository.url == repo_url))
    repo_id = result.scalar_one_or_none()
    if repo_id is None:
        raise HTTPException(status_code=404, detail=f"Repository not found: {repo_url}")
    return repo_id


class ListFilesRequest(BaseModel):
    repo_url: str
    glob: str | None = None


@router.post("/list_files")
async def list_files(body: ListFilesRequest, db: AsyncSession = Depends(get_db)):
    repo_id = await get_repo_id(body.repo_url, db)
    query = select(File.filePath).where(File.repository_id == repo_id)
    result = await db.execute(query)
    paths = [row[0] for row in result.all()]

    if body.glob:
        paths = [p for p in paths if fnmatch(p, body.glob)]

    return {"files": sorted(paths)}


class ReadFileRequest(BaseModel):
    repo_url: str
    path: str
    start: int | None = None
    end: int | None = None


@router.post("/read_file")
async def read_file(body: ReadFileRequest, db: AsyncSession = Depends(get_db)):
    repo_id = await get_repo_id(body.repo_url, db)
    result = await db.execute(
        select(File.content).where(
            File.repository_id == repo_id,
            File.filePath == body.path,
        )
    )
    content = result.scalar_one_or_none()
    if content is None:
        raise HTTPException(status_code=404, detail=f"File not found: {body.path}")

    lines = content.splitlines()
    start = (body.start or 1) - 1  # convert to 0-indexed
    end = body.end or len(lines)

    return {
        "path": body.path,
        "start": start + 1,
        "end": min(end, len(lines)),
        "total_lines": len(lines),
        "content": "\n".join(lines[start:end]),
    }


class SearchCodeRequest(BaseModel):
    repo_url: str
    query: str
    file_type: str | None = None


@router.post("/search_code")
async def search_code(body: SearchCodeRequest, db: AsyncSession = Depends(get_db)):
    repo_id = await get_repo_id(body.repo_url, db)
    query = select(File.filePath, File.content).where(File.repository_id == repo_id)
    result = await db.execute(query)
    files = result.all()

    try:
        pattern = re.compile(body.query, re.IGNORECASE)
    except re.error:
        raise HTTPException(status_code=400, detail=f"Invalid regex: {body.query}")

    matches = []
    for file_path, content in files:
        if body.file_type and not file_path.endswith(body.file_type):
            continue

        for i, line in enumerate(content.splitlines(), 1):
            if pattern.search(line):
                matches.append({
                    "file": file_path,
                    "line": i,
                    "content": line.strip(),
                })

    return {"matches": matches, "count": len(matches)}


class FindReferencesRequest(BaseModel):
    repo_url: str
    symbol: str


@router.post("/find_references")
async def find_references(body: FindReferencesRequest, db: AsyncSession = Depends(get_db)):
    repo_id = await get_repo_id(body.repo_url, db)
    result = await db.execute(
        select(Chunk, File.filePath)
        .join(File)
        .where(
            File.repository_id == repo_id,
            Chunk.name == body.symbol,
            Chunk.chunk_type.in_(["function", "class"]),
        )
    )
    rows = result.all()

    matches = [
        {
            "file_path": file_path,
            "line": chunk.start_line,
            "end_line": chunk.end_line,
            "chunk_type": chunk.chunk_type,
        }
        for chunk, file_path in rows
    ]

    return {"symbol": body.symbol, "matches": matches}


class GetDependenciesRequest(BaseModel):
    repo_url: str
    path: str


@router.post("/get_dependencies")
async def get_dependencies(body: GetDependenciesRequest, db: AsyncSession = Depends(get_db)):
    repo_id = await get_repo_id(body.repo_url, db)
    result = await db.execute(
        select(Chunk.content)
        .join(File)
        .where(
            File.repository_id == repo_id,
            File.filePath == body.path,
            Chunk.chunk_type == "import",
        )
    )
    imports = [row[0] for row in result.all()]

    return {"path": body.path, "imports": imports}


class SearchIndexedRequest(BaseModel):
    repo_url: str
    query: str
    limit: int = 10


@router.post("/search_indexed")
async def search_indexed(body: SearchIndexedRequest, db: AsyncSession = Depends(get_db)):
    repo_id = await get_repo_id(body.repo_url, db)

    openai_client = OpenAI(api_key=settings.openai_api_key)
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=[body.query],
    )
    query_embedding = response.data[0].embedding

    result = await db.execute(
        select(Chunk, File.filePath)
        .join(File)
        .where(File.repository_id == repo_id)
        .order_by(Chunk.embedding.cosine_distance(query_embedding))
        .limit(body.limit)
    )
    rows = result.all()

    return {
        "query": body.query,
        "results": [
            {
                "content": chunk.content,
                "chunk_type": chunk.chunk_type,
                "name": chunk.name,
                "file_path": file_path,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
            }
            for chunk, file_path in rows
        ],
    }
