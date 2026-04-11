import aiosqlite


async def list_servers(db: aiosqlite.Connection) -> list[dict]:
    rows = await db.execute_fetchall(
        "SELECT id, name, api_url, api_key, server_id, is_active, created_at, updated_at "
        "FROM pdns_servers ORDER BY name ASC"
    )
    return [_row_to_dict(r) for r in rows]


async def get_server(db: aiosqlite.Connection, server_db_id: int) -> dict | None:
    rows = await db.execute_fetchall(
        "SELECT id, name, api_url, api_key, server_id, is_active, created_at, updated_at "
        "FROM pdns_servers WHERE id = ?",
        (server_db_id,),
    )
    return _row_to_dict(rows[0]) if rows else None


async def create_server(
    db: aiosqlite.Connection,
    name: str,
    api_url: str,
    api_key: str,
    server_id: str,
) -> dict:
    cursor = await db.execute(
        "INSERT INTO pdns_servers (name, api_url, api_key, server_id) VALUES (?, ?, ?, ?)",
        (name, api_url, api_key, server_id),
    )
    await db.commit()
    return await get_server(db, cursor.lastrowid)


async def update_server(
    db: aiosqlite.Connection,
    server_db_id: int,
    name: str,
    api_url: str,
    api_key: str,
    server_id: str,
    is_active: bool,
) -> dict | None:
    await db.execute(
        "UPDATE pdns_servers SET name=?, api_url=?, api_key=?, server_id=?, is_active=?, "
        "updated_at=datetime('now') WHERE id=?",
        (name, api_url, api_key, server_id, 1 if is_active else 0, server_db_id),
    )
    await db.commit()
    return await get_server(db, server_db_id)


async def delete_server(db: aiosqlite.Connection, server_db_id: int) -> None:
    await db.execute("DELETE FROM pdns_servers WHERE id = ?", (server_db_id,))
    await db.commit()


async def get_server_for_zone(db: aiosqlite.Connection, zone_name: str) -> dict | None:
    rows = await db.execute_fetchall(
        "SELECT s.id, s.name, s.api_url, s.api_key, s.server_id, s.is_active, s.created_at, s.updated_at "
        "FROM pdns_servers s JOIN zone_server_map m ON s.id = m.pdns_server_id "
        "WHERE m.zone_name = ?",
        (zone_name,),
    )
    return _row_to_dict(rows[0]) if rows else None


async def map_zone_to_server(
    db: aiosqlite.Connection, zone_name: str, pdns_server_id: int
) -> None:
    await db.execute(
        "INSERT INTO zone_server_map (zone_name, pdns_server_id) VALUES (?, ?) "
        "ON CONFLICT(zone_name, pdns_server_id) DO NOTHING",
        (zone_name, pdns_server_id),
    )
    await db.commit()


async def unmap_zone(db: aiosqlite.Connection, zone_name: str) -> None:
    await db.execute("DELETE FROM zone_server_map WHERE zone_name = ?", (zone_name,))
    await db.commit()


async def unmap_zone_from_server(
    db: aiosqlite.Connection, zone_name: str, pdns_server_id: int
) -> None:
    await db.execute(
        "DELETE FROM zone_server_map WHERE zone_name = ? AND pdns_server_id = ?",
        (zone_name, pdns_server_id),
    )
    await db.commit()


async def count_zone_servers(db: aiosqlite.Connection, zone_name: str) -> int:
    rows = await db.execute_fetchall(
        "SELECT COUNT(*) FROM zone_server_map WHERE zone_name = ?",
        (zone_name,),
    )
    return rows[0][0] if rows else 0


async def get_server_for_zone_by_server_id(
    db: aiosqlite.Connection, zone_name: str, pdns_server_db_id: int
) -> dict | None:
    rows = await db.execute_fetchall(
        "SELECT s.id, s.name, s.api_url, s.api_key, s.server_id, s.is_active, s.created_at, s.updated_at "
        "FROM pdns_servers s JOIN zone_server_map m ON s.id = m.pdns_server_id "
        "WHERE m.zone_name = ? AND s.id = ?",
        (zone_name, pdns_server_db_id),
    )
    return _row_to_dict(rows[0]) if rows else None


async def get_server_for_zone_or_fallback(
    db: aiosqlite.Connection, zone_name: str
) -> dict | None:
    """Return mapped server for zone. If unmapped and exactly one active server exists,
    auto-map the zone to it (handles zones created before multi-pdns migration).
    With multiple active servers and no mapping, returns the first active server."""
    srv = await get_server_for_zone(db, zone_name)
    if srv is not None:
        return srv
    active = [s for s in await list_servers(db) if s["is_active"]]
    if len(active) == 1:
        await map_zone_to_server(db, zone_name, active[0]["id"])
        return active[0]
    if active:
        return active[0]
    return None


async def list_zones_for_server(
    db: aiosqlite.Connection, server_db_id: int
) -> list[str]:
    rows = await db.execute_fetchall(
        "SELECT zone_name FROM zone_server_map WHERE pdns_server_id = ?",
        (server_db_id,),
    )
    return [r[0] for r in rows]


def _row_to_dict(row) -> dict:
    return {
        "id": row[0],
        "name": row[1],
        "api_url": row[2],
        "api_key": row[3],
        "server_id": row[4],
        "is_active": bool(row[5]),
        "created_at": row[6],
        "updated_at": row[7],
    }
