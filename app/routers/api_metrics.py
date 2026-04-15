import asyncio

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from app.auth import get_current_user, get_session_user, require_admin
from app.database import get_db
from app.models.user import User
from app.pdns_client import PDNSError, registry
from app.repositories import pdns_server_repo

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("")
async def get_metrics_overview(
    user: User = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    servers = await pdns_server_repo.list_servers(db)
    active = [s for s in servers if s["is_active"]]

    async def _fetch(srv):
        entry = {
            "id": srv["id"],
            "name": srv["name"],
            "connected": False,
            "version": None,
            "zone_count": 0,
            "dnssec_count": 0,
            "uptime": None,
        }
        try:
            client = registry.get(srv["id"])
            info, zones = await asyncio.gather(
                client.get_server_info(),
                client.list_zones(),
            )
            entry["connected"] = True
            entry["version"] = info.get("version")
            entry["zone_count"] = len(zones)
            entry["dnssec_count"] = sum(1 for z in zones if z.get("dnssec"))
        except (PDNSError, RuntimeError):
            pass
        return entry

    results = await asyncio.gather(*[_fetch(s) for s in active])
    return list(results)


@router.get("/{server_db_id}")
async def get_server_metrics(
    server_db_id: int,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    srv = await pdns_server_repo.get_server(db, server_db_id)
    if srv is None or not srv["is_active"]:
        raise HTTPException(404, "Server not found")
    try:
        client = registry.get(server_db_id)
    except RuntimeError:
        raise HTTPException(503, f"Server '{srv['name']}' not connected")
    try:
        info, stats = await asyncio.gather(
            client.get_server_info(),
            client.get_statistics(),
        )
    except PDNSError as exc:
        raise HTTPException(exc.status_code, exc.detail)
    return {"server_info": info, "statistics": stats}


@router.websocket("/ws/{server_db_id}")
async def ws_server_metrics(
    websocket: WebSocket,
    server_db_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    session_id = websocket.cookies.get("session_id")
    user = await get_session_user(db, session_id) if session_id else None
    if not user or not user.is_active or user.role != "admin":
        await websocket.close(code=4401)
        return

    srv = await pdns_server_repo.get_server(db, server_db_id)
    if srv is None or not srv["is_active"]:
        await websocket.close(code=4404)
        return

    try:
        client = registry.get(server_db_id)
    except RuntimeError:
        await websocket.close(code=4503)
        return

    await websocket.accept()
    try:
        while True:
            try:
                info, stats = await asyncio.gather(
                    client.get_server_info(),
                    client.get_statistics(),
                )
                await websocket.send_json({"server_info": info, "statistics": stats})
            except PDNSError as exc:
                await websocket.send_json({"error": exc.detail})
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
