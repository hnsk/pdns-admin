import aiosqlite


async def get_setting(db: aiosqlite.Connection, key: str) -> str | None:
    rows = await db.execute_fetchall("SELECT value FROM settings WHERE key = ?", (key,))
    return rows[0][0] if rows else None


async def upsert_setting(db: aiosqlite.Connection, key: str, value: str) -> None:
    await db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    await db.commit()


async def seed_defaults(db: aiosqlite.Connection, defaults: dict[str, str]) -> None:
    """Insert default values only if keys do not already exist."""
    for key, value in defaults.items():
        await db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO NOTHING",
            (key, value),
        )
    await db.commit()


async def get_pdns_settings(db: aiosqlite.Connection) -> dict[str, str]:
    rows = await db.execute_fetchall(
        "SELECT key, value FROM settings WHERE key IN ('pdns_api_url', 'pdns_api_key', 'pdns_server_id')"
    )
    return {r[0]: r[1] for r in rows}
