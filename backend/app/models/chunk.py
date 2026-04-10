from datetime import datetime
from sqlalchemy import String, Text, DateTime, Integer, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from typing import Optional
from app.models.base import Base


class Chunk(Base):
    __tablename__ = "chunk"

    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    chunk_type: Mapped[str] = mapped_column(String(50))  # "code", "import", "function", "class", "interface", "struct"
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    embedding = mapped_column(Vector(1536))  # OpenAI text-embedding-3-small dimension
    file_id: Mapped[int] = mapped_column(ForeignKey("file.id"))
    file: Mapped["File"] = relationship(back_populates="chunks")
    created_at: Mapped[datetime] = mapped_column(DateTime)

    __table_args__ = (
        Index("ix_chunk_name", "name"),
    )
