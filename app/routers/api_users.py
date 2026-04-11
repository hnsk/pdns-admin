from fastapi import APIRouter, Depends, HTTPException

import aiosqlite

from app.auth import require_admin, get_current_user
from app.database import get_db
from app.models.user import User, UserCreate, UserUpdate
from app.repositories import user_repo, zone_assignment_repo, audit_repo

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("")
async def list_users(user: User = Depends(require_admin), db: aiosqlite.Connection = Depends(get_db)):
    return [u.model_dump() for u in await user_repo.list_users(db)]


@router.post("", status_code=201)
async def create_user(
    body: UserCreate,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    existing = await user_repo.get_user_by_username(db, body.username)
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")
    if body.role not in ("admin", "operator"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'operator'")

    new_user = await user_repo.create_user(db, body.username, body.password, body.role)
    await audit_repo.log_action(
        db, user.id, user.username, "user.create",
        detail={"new_username": body.username, "role": body.role},
    )
    return new_user.model_dump()


@router.get("/{user_id}")
async def get_user(user_id: int, user: User = Depends(require_admin), db: aiosqlite.Connection = Depends(get_db)):
    target = await user_repo.get_user_by_id(db, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    zones = await zone_assignment_repo.get_user_zones(db, user_id)
    return {**target.model_dump(), "zones": zones}


@router.put("/{user_id}")
async def update_user(
    user_id: int,
    body: UserUpdate,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    target = await user_repo.get_user_by_id(db, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if body.role and body.role not in ("admin", "operator"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'operator'")

    await user_repo.update_user(db, user_id, password=body.password, role=body.role, is_active=body.is_active)
    await audit_repo.log_action(
        db, user.id, user.username, "user.update",
        detail={"target_user": target.username, "changes": body.model_dump(exclude_none=True, exclude={"password"})},
    )
    return {"ok": True}


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    if user_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    target = await user_repo.get_user_by_id(db, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    await user_repo.delete_user(db, user_id)
    await audit_repo.log_action(
        db, user.id, user.username, "user.delete", detail={"deleted_user": target.username},
    )
    return {"ok": True}


@router.put("/{user_id}/zones")
async def set_user_zones(
    user_id: int,
    zone_names: list[str],
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    target = await user_repo.get_user_by_id(db, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    await zone_assignment_repo.set_user_zones(db, user_id, zone_names)
    await audit_repo.log_action(
        db, user.id, user.username, "user.zones_update",
        detail={"target_user": target.username, "zones": zone_names},
    )
    return {"ok": True}


@router.get("/{user_id}/zones")
async def get_user_zones(
    user_id: int,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    return await zone_assignment_repo.get_user_zones(db, user_id)


@router.put("/me/password")
async def change_own_password(
    new_password: str,
    user: User = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    await user_repo.update_user(db, user.id, password=new_password)
    await audit_repo.log_action(db, user.id, user.username, "user.password_change")
    return {"ok": True}
