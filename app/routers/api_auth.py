from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

import aiosqlite

from app.auth import create_session, delete_session, get_current_user, create_api_key, list_api_keys, delete_api_key
from app.database import get_db
from app.models.user import LoginRequest, User
from app.repositories import user_repo, audit_repo

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/login")
async def login(body: LoginRequest, db: aiosqlite.Connection = Depends(get_db)):
    user = await user_repo.verify_password(db, body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    session_id = await create_session(db, user.id)
    await audit_repo.log_action(db, user.id, user.username, "auth.login")

    response = JSONResponse({"ok": True, "user": user.model_dump()})
    response.set_cookie("session_id", session_id, httponly=True, samesite="lax", max_age=3600 * 8)
    return response


@router.post("/logout")
async def logout(
    user: User = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    from fastapi import Request
    # Session cleanup handled by cookie removal
    await audit_repo.log_action(db, user.id, user.username, "auth.logout")
    response = JSONResponse({"ok": True})
    response.delete_cookie("session_id")
    return response


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    return user.model_dump()


@router.post("/api-keys")
async def create_key(
    description: str = "",
    user: User = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    key = await create_api_key(db, user.id, description)
    await audit_repo.log_action(db, user.id, user.username, "apikey.create", detail={"description": description})
    return {"key": key, "description": description}


@router.get("/api-keys")
async def list_keys(user: User = Depends(get_current_user), db: aiosqlite.Connection = Depends(get_db)):
    return await list_api_keys(db, user.id)


@router.delete("/api-keys/{key_id}")
async def remove_key(
    key_id: int,
    user: User = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    await delete_api_key(db, key_id, user.id)
    await audit_repo.log_action(db, user.id, user.username, "apikey.delete", detail={"key_id": key_id})
    return {"ok": True}
