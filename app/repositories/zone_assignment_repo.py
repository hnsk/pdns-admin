import aiosqlite


async def get_user_zones(db: aiosqlite.Connection, user_id: int) -> list[str]:
    rows = await db.execute_fetchall("SELECT zone_name FROM zone_assignments WHERE user_id = ?", (user_id,))
    return [r[0] for r in rows]


async def get_zone_users(db: aiosqlite.Connection, zone_name: str) -> list[int]:
    rows = await db.execute_fetchall("SELECT user_id FROM zone_assignments WHERE zone_name = ?", (zone_name,))
    return [r[0] for r in rows]


async def assign_zone(db: aiosqlite.Connection, user_id: int, zone_name: str) -> None:
    await db.execute(
        "INSERT OR IGNORE INTO zone_assignments (user_id, zone_name) VALUES (?, ?)",
        (user_id, zone_name),
    )
    await db.commit()


async def unassign_zone(db: aiosqlite.Connection, user_id: int, zone_name: str) -> None:
    await db.execute("DELETE FROM zone_assignments WHERE user_id = ? AND zone_name = ?", (user_id, zone_name))
    await db.commit()


async def set_user_zones(db: aiosqlite.Connection, user_id: int, zone_names: list[str]) -> None:
    await db.execute("DELETE FROM zone_assignments WHERE user_id = ?", (user_id,))
    for zn in zone_names:
        await db.execute("INSERT INTO zone_assignments (user_id, zone_name) VALUES (?, ?)", (user_id, zn))
    await db.commit()


async def user_has_zone_access(db: aiosqlite.Connection, user_id: int, zone_name: str) -> bool:
    rows = await db.execute_fetchall(
        "SELECT 1 FROM zone_assignments WHERE user_id = ? AND zone_name = ?", (user_id, zone_name)
    )
    return len(rows) > 0
