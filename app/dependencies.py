from fastapi import Depends, HTTPException, Query

import aiosqlite

from app.database import get_db
from app.pdns_client import PDNSClient, registry
from app.repositories import pdns_server_repo


async def get_pdns_for_zone(
    zone_id: str,
    server_id: int | None = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
) -> PDNSClient:
    if server_id is not None:
        srv = await pdns_server_repo.get_server_for_zone_by_server_id(db, zone_id, server_id)
        if srv is None:
            raise HTTPException(404, "Zone not mapped to the specified server")
    else:
        srv = await pdns_server_repo.get_server_for_zone_or_fallback(db, zone_id)
        if srv is None:
            raise HTTPException(404, "Zone not mapped to any server")
    try:
        return registry.get(srv["id"])
    except RuntimeError:
        raise HTTPException(503, f"PowerDNS server '{srv['name']}' is not connected")
