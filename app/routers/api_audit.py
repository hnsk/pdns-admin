from fastapi import APIRouter, Depends, Query

import aiosqlite

from app.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.repositories import audit_repo

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
async def get_audit_log(
    zone_name: str | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    # Operators can only see their own actions
    user_id_filter = None if user.role == "admin" else user.id
    entries = await audit_repo.get_audit_log(db, zone_name=zone_name, user_id=user_id_filter, limit=limit, offset=offset)
    total = await audit_repo.count_audit_log(db, zone_name=zone_name, user_id=user_id_filter)
    return {"entries": [e.model_dump() for e in entries], "total": total}
