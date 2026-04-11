import json

import aiosqlite

from app.models.audit import AuditEntry


async def log_action(
    db: aiosqlite.Connection,
    user_id: int | None,
    username: str | None,
    action: str,
    zone_name: str | None = None,
    detail: dict | str | None = None,
) -> None:
    detail_str = json.dumps(detail) if isinstance(detail, dict) else detail
    await db.execute(
        "INSERT INTO audit_log (user_id, username, action, zone_name, detail) VALUES (?, ?, ?, ?, ?)",
        (user_id, username, action, zone_name, detail_str),
    )
    await db.commit()


async def get_audit_log(
    db: aiosqlite.Connection,
    zone_name: str | None = None,
    user_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditEntry]:
    conditions = []
    params: list = []
    if zone_name:
        conditions.append("zone_name = ?")
        params.append(zone_name)
    if user_id:
        conditions.append("user_id = ?")
        params.append(user_id)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.extend([limit, offset])

    rows = await db.execute_fetchall(
        f"SELECT id, user_id, username, action, zone_name, detail, created_at FROM audit_log {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params,
    )
    return [
        AuditEntry(id=r[0], user_id=r[1], username=r[2], action=r[3], zone_name=r[4], detail=r[5], created_at=r[6])
        for r in rows
    ]


async def count_audit_log(
    db: aiosqlite.Connection,
    zone_name: str | None = None,
    user_id: int | None = None,
) -> int:
    conditions = []
    params: list = []
    if zone_name:
        conditions.append("zone_name = ?")
        params.append(zone_name)
    if user_id:
        conditions.append("user_id = ?")
        params.append(user_id)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await db.execute_fetchall(f"SELECT COUNT(*) FROM audit_log {where}", params)
    return rows[0][0]
