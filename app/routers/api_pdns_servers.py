import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

import aiosqlite

from app.auth import require_admin
from app.database import get_db
from app.models.user import User
from app.pdns_client import registry
from app.repositories import audit_repo, pdns_server_repo, zone_assignment_repo

router = APIRouter(prefix="/api/pdns-servers", tags=["pdns-servers"])


class PDNSServerCreate(BaseModel):
    name: str
    api_url: str
    api_key: str
    server_id: str


class PDNSServerUpdate(BaseModel):
    name: str
    api_url: str
    api_key: str
    server_id: str
    is_active: bool = True


def _strip_key(srv: dict) -> dict:
    return {k: v for k, v in srv.items() if k != "api_key"}


@router.get("")
async def list_servers(
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    servers = await pdns_server_repo.list_servers(db)
    return [_strip_key(s) for s in servers]


@router.post("", status_code=201)
async def create_server(
    body: PDNSServerCreate,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    if not body.api_url.startswith(("http://", "https://")):
        raise HTTPException(400, "api_url must start with http:// or https://")
    srv = await pdns_server_repo.create_server(
        db, body.name, body.api_url, body.api_key, body.server_id
    )
    try:
        await registry.start_server(srv["id"], srv["api_url"], srv["api_key"], srv["server_id"])
    except Exception as exc:
        import logging
        logging.warning("Failed to connect to %s: %s", srv["name"], exc)
    await audit_repo.log_action(
        db, user.id, user.username, "pdns_server.create",
        detail={"name": srv["name"], "api_url": srv["api_url"], "server_id": srv["server_id"]},
    )
    return _strip_key(srv)


@router.get("/{server_id}")
async def get_server(
    server_id: int,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    srv = await pdns_server_repo.get_server(db, server_id)
    if srv is None:
        raise HTTPException(404, "Server not found")
    return _strip_key(srv)


@router.put("/{server_id}")
async def update_server(
    server_id: int,
    body: PDNSServerUpdate,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    if not body.api_url.startswith(("http://", "https://")):
        raise HTTPException(400, "api_url must start with http:// or https://")

    existing = await pdns_server_repo.get_server(db, server_id)
    if existing is None:
        raise HTTPException(404, "Server not found")

    api_key = body.api_key if body.api_key else existing["api_key"]

    srv = await pdns_server_repo.update_server(
        db, server_id, body.name, body.api_url, api_key, body.server_id, body.is_active
    )
    if body.is_active:
        try:
            await registry.reconfigure_server(
                server_id, srv["api_url"], srv["api_key"], srv["server_id"]
            )
        except Exception as exc:
            import logging
            logging.warning("Failed to reconfigure %s: %s", srv["name"], exc)
    else:
        await registry.stop_server(server_id)

    await audit_repo.log_action(
        db, user.id, user.username, "pdns_server.update",
        detail={"name": srv["name"], "api_url": srv["api_url"], "server_id": srv["server_id"], "is_active": body.is_active},
    )
    return _strip_key(srv)


@router.delete("/{server_id}")
async def delete_server(
    server_id: int,
    cascade: bool = Query(False),
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    existing = await pdns_server_repo.get_server(db, server_id)
    if existing is None:
        raise HTTPException(404, "Server not found")

    zones = await pdns_server_repo.list_zones_for_server(db, server_id)
    if zones and not cascade:
        raise HTTPException(409, detail={"detail": "Server has mapped zones", "zones": zones})

    if zones:
        for zone_name in zones:
            await pdns_server_repo.unmap_zone(db, zone_name)
            await zone_assignment_repo.delete_zone_assignments(db, zone_name)

    await pdns_server_repo.delete_server(db, server_id)
    await registry.stop_server(server_id)

    await audit_repo.log_action(
        db, user.id, user.username, "pdns_server.delete",
        detail={"name": existing["name"], "cascade": cascade},
    )
    return {"ok": True}


@router.post("/test")
async def test_new_server(
    body: PDNSServerCreate,
    user: User = Depends(require_admin),
):
    return await _test_connection(body.api_url, body.api_key, body.server_id)


@router.post("/{server_id}/test")
async def test_existing_server(
    server_id: int,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    srv = await pdns_server_repo.get_server(db, server_id)
    if srv is None:
        raise HTTPException(404, "Server not found")
    return await _test_connection(srv["api_url"], srv["api_key"], srv["server_id"])


async def _test_connection(api_url: str, api_key: str, server_id: str) -> dict:
    if not api_url.startswith(("http://", "https://")):
        raise HTTPException(400, "api_url must start with http:// or https://")
    url = f"{api_url.rstrip('/')}/api/v1/servers/{server_id}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers={"X-API-Key": api_key})
        if resp.status_code == 200:
            return {"status": "ok", "detail": f"Connected to {resp.json().get('type', 'PowerDNS')}"}
        elif resp.status_code == 401:
            raise HTTPException(401, "Authentication failed — check API key")
        elif resp.status_code == 404:
            raise HTTPException(404, "Server ID not found — check server ID")
        else:
            raise HTTPException(resp.status_code, f"PowerDNS returned {resp.status_code}")
    except httpx.ConnectError:
        raise HTTPException(502, "Cannot reach PowerDNS — check API URL")
    except httpx.TimeoutException:
        raise HTTPException(504, "Connection timed out — check API URL")
