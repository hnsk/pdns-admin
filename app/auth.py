import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import aiosqlite
from fastapi import Depends, HTTPException, Request

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.repositories import user_repo, zone_assignment_repo


async def create_session(db: aiosqlite.Connection, user_id: int) -> str:
    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.session_lifetime_hours)
    await db.execute(
        "INSERT INTO sessions (id, user_id, expires_at) VALUES (?, ?, ?)",
        (session_id, user_id, expires_at.isoformat()),
    )
    await db.commit()
    return session_id


async def get_session_user(db: aiosqlite.Connection, session_id: str) -> User | None:
    rows = await db.execute_fetchall(
        "SELECT user_id, expires_at FROM sessions WHERE id = ?", (session_id,)
    )
    if not rows:
        return None
    user_id, expires_at = rows[0][0], rows[0][1]
    if datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
        await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await db.commit()
        return None
    return await user_repo.get_user_by_id(db, user_id)


async def delete_session(db: aiosqlite.Connection, session_id: str) -> None:
    await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    await db.commit()


async def cleanup_expired_sessions(db: aiosqlite.Connection) -> None:
    await db.execute("DELETE FROM sessions WHERE expires_at < ?", (datetime.now(timezone.utc).isoformat(),))
    await db.commit()


async def verify_api_key(db: aiosqlite.Connection, key: str) -> User | None:
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    rows = await db.execute_fetchall("SELECT user_id FROM api_keys WHERE key_hash = ?", (key_hash,))
    if not rows:
        return None
    return await user_repo.get_user_by_id(db, rows[0][0])


async def create_api_key(db: aiosqlite.Connection, user_id: int, description: str = "") -> str:
    key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    await db.execute(
        "INSERT INTO api_keys (user_id, key_hash, description) VALUES (?, ?, ?)",
        (user_id, key_hash, description),
    )
    await db.commit()
    return key


async def list_api_keys(db: aiosqlite.Connection, user_id: int) -> list[dict]:
    rows = await db.execute_fetchall(
        "SELECT id, description, created_at FROM api_keys WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    return [{"id": r[0], "description": r[1], "created_at": r[2]} for r in rows]


async def delete_api_key(db: aiosqlite.Connection, key_id: int, user_id: int) -> None:
    await db.execute("DELETE FROM api_keys WHERE id = ? AND user_id = ?", (key_id, user_id))
    await db.commit()


async def get_current_user(request: Request, db: aiosqlite.Connection = Depends(get_db)) -> User:
    # Check API key header first
    api_key = request.headers.get("X-API-Key")
    if api_key:
        user = await verify_api_key(db, api_key)
        if user and user.is_active:
            return user
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Check session cookie
    session_id = request.cookies.get("session_id")
    if not session_id:
        if _is_api_request(request):
            raise HTTPException(status_code=401, detail="Not authenticated")
        from fastapi.responses import RedirectResponse
        raise HTTPException(status_code=307, headers={"Location": "/login"})

    user = await get_session_user(db, session_id)
    if not user or not user.is_active:
        if _is_api_request(request):
            raise HTTPException(status_code=401, detail="Session expired")
        raise HTTPException(status_code=307, headers={"Location": "/login"})
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def require_zone_access(
    zone_id: str, user: User = Depends(get_current_user), db: aiosqlite.Connection = Depends(get_db)
) -> User:
    if user.role == "admin":
        return user
    if await zone_assignment_repo.user_has_zone_access(db, user.id, zone_id):
        return user
    raise HTTPException(status_code=403, detail="No access to this zone")


def _is_api_request(request: Request) -> bool:
    return request.url.path.startswith("/api/")
