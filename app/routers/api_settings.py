from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import aiosqlite

from app.auth import require_admin
from app.database import get_db
from app.models.user import User
from app.repositories import settings_repo

router = APIRouter(prefix="/api/settings", tags=["settings"])


class DefaultTTLUpdate(BaseModel):
    value: int


@router.get("/default-record-ttl")
async def get_default_record_ttl(
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    raw = await settings_repo.get_setting(db, "default_record_ttl")
    return {"value": int(raw) if raw is not None else 60}


@router.put("/default-record-ttl")
async def set_default_record_ttl(
    body: DefaultTTLUpdate,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    if body.value < 1:
        raise HTTPException(status_code=400, detail="TTL must be at least 1")
    await settings_repo.upsert_setting(db, "default_record_ttl", str(body.value))
    return {"value": body.value}
