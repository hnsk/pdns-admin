import bcrypt
import aiosqlite

from app.models.user import User


async def get_user_by_id(db: aiosqlite.Connection, user_id: int) -> User | None:
    row = await db.execute_fetchall("SELECT id, username, role, is_active, default_ttl FROM users WHERE id = ?", (user_id,))
    if not row:
        return None
    r = row[0]
    return User(id=r[0], username=r[1], role=r[2], is_active=bool(r[3]), default_ttl=r[4])


async def get_user_by_username(db: aiosqlite.Connection, username: str) -> User | None:
    row = await db.execute_fetchall("SELECT id, username, role, is_active, default_ttl FROM users WHERE username = ?", (username,))
    if not row:
        return None
    r = row[0]
    return User(id=r[0], username=r[1], role=r[2], is_active=bool(r[3]), default_ttl=r[4])


async def verify_password(db: aiosqlite.Connection, username: str, password: str) -> User | None:
    row = await db.execute_fetchall(
        "SELECT id, username, password_hash, role, is_active FROM users WHERE username = ?", (username,)
    )
    if not row:
        return None
    r = row[0]
    if not bcrypt.checkpw(password.encode(), r[2].encode()):
        return None
    if not r[4]:
        return None
    return User(id=r[0], username=r[1], role=r[3], is_active=bool(r[4]))


async def create_user(db: aiosqlite.Connection, username: str, password: str, role: str = "operator") -> User:
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    cursor = await db.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        (username, pw_hash, role),
    )
    await db.commit()
    return User(id=cursor.lastrowid, username=username, role=role, is_active=True)


async def update_user(
    db: aiosqlite.Connection, user_id: int, password: str | None = None, role: str | None = None, is_active: bool | None = None
) -> None:
    updates = []
    params = []
    if password is not None:
        updates.append("password_hash = ?")
        params.append(bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode())
    if role is not None:
        updates.append("role = ?")
        params.append(role)
    if is_active is not None:
        updates.append("is_active = ?")
        params.append(int(is_active))
    if updates:
        updates.append("updated_at = datetime('now')")
        params.append(user_id)
        await db.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
        await db.commit()


async def update_user_preferences(db: aiosqlite.Connection, user_id: int, default_ttl: int | None) -> None:
    await db.execute(
        "UPDATE users SET default_ttl = ?, updated_at = datetime('now') WHERE id = ?",
        (default_ttl, user_id),
    )
    await db.commit()


async def delete_user(db: aiosqlite.Connection, user_id: int) -> None:
    await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    await db.commit()


async def list_users(db: aiosqlite.Connection) -> list[User]:
    rows = await db.execute_fetchall("SELECT id, username, role, is_active, default_ttl FROM users ORDER BY username")
    return [User(id=r[0], username=r[1], role=r[2], is_active=bool(r[3])) for r in rows]


async def ensure_admin_exists(db: aiosqlite.Connection, default_password: str) -> None:
    rows = await db.execute_fetchall("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
    if not rows:
        await create_user(db, "admin", default_password, "admin")
