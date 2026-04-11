import json

import aiosqlite


async def list_templates(db: aiosqlite.Connection) -> list[dict]:
    rows = await db.execute_fetchall(
        "SELECT id, name, nameservers, soa_mname, soa_rname, soa_refresh, soa_retry, soa_expire, soa_ttl, is_default, created_at "
        "FROM zone_templates ORDER BY is_default DESC, name ASC"
    )
    return [_row_to_dict(r) for r in rows]


async def get_template(db: aiosqlite.Connection, template_id: int) -> dict | None:
    rows = await db.execute_fetchall(
        "SELECT id, name, nameservers, soa_mname, soa_rname, soa_refresh, soa_retry, soa_expire, soa_ttl, is_default, created_at "
        "FROM zone_templates WHERE id = ?",
        (template_id,),
    )
    return _row_to_dict(rows[0]) if rows else None


async def get_default_template(db: aiosqlite.Connection) -> dict | None:
    rows = await db.execute_fetchall(
        "SELECT id, name, nameservers, soa_mname, soa_rname, soa_refresh, soa_retry, soa_expire, soa_ttl, is_default, created_at "
        "FROM zone_templates WHERE is_default = 1 LIMIT 1"
    )
    return _row_to_dict(rows[0]) if rows else None


async def create_template(
    db: aiosqlite.Connection,
    name: str,
    nameservers: list[str],
    soa_mname: str,
    soa_rname: str,
    soa_refresh: int,
    soa_retry: int,
    soa_expire: int,
    soa_ttl: int,
    is_default: bool = False,
) -> dict:
    if is_default:
        await db.execute("UPDATE zone_templates SET is_default = 0")
    cursor = await db.execute(
        "INSERT INTO zone_templates (name, nameservers, soa_mname, soa_rname, soa_refresh, soa_retry, soa_expire, soa_ttl, is_default) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, json.dumps(nameservers), soa_mname, soa_rname, soa_refresh, soa_retry, soa_expire, soa_ttl, 1 if is_default else 0),
    )
    await db.commit()
    return await get_template(db, cursor.lastrowid)


async def update_template(
    db: aiosqlite.Connection,
    template_id: int,
    name: str,
    nameservers: list[str],
    soa_mname: str,
    soa_rname: str,
    soa_refresh: int,
    soa_retry: int,
    soa_expire: int,
    soa_ttl: int,
    is_default: bool = False,
) -> dict | None:
    if is_default:
        await db.execute("UPDATE zone_templates SET is_default = 0")
    await db.execute(
        "UPDATE zone_templates SET name=?, nameservers=?, soa_mname=?, soa_rname=?, soa_refresh=?, soa_retry=?, soa_expire=?, soa_ttl=?, is_default=? "
        "WHERE id=?",
        (name, json.dumps(nameservers), soa_mname, soa_rname, soa_refresh, soa_retry, soa_expire, soa_ttl, 1 if is_default else 0, template_id),
    )
    await db.commit()
    return await get_template(db, template_id)


async def set_default(db: aiosqlite.Connection, template_id: int) -> None:
    await db.execute("UPDATE zone_templates SET is_default = 0")
    await db.execute("UPDATE zone_templates SET is_default = 1 WHERE id = ?", (template_id,))
    await db.commit()


async def delete_template(db: aiosqlite.Connection, template_id: int) -> None:
    await db.execute("DELETE FROM zone_templates WHERE id = ?", (template_id,))
    await db.commit()


def _row_to_dict(row) -> dict:
    return {
        "id": row[0],
        "name": row[1],
        "nameservers": json.loads(row[2]),
        "soa_mname": row[3],
        "soa_rname": row[4],
        "soa_refresh": row[5],
        "soa_retry": row[6],
        "soa_expire": row[7],
        "soa_ttl": row[8],
        "is_default": bool(row[9]),
        "created_at": row[10],
    }
