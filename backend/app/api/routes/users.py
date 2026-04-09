from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models.user import User

router = APIRouter()


@router.post("/users")
async def create_user(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(func.count()).select_from(User))
    num_users = result.scalar_one()
    new_user = User(name=f"User {num_users + 1}")
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return {"id": new_user.id, "name": new_user.name}
