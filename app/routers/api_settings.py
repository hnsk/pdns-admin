from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import aiosqlite

from app.auth import require_admin
from app.database import get_db
from app.models.user import User
from app.pdns_client import pdns
from app.repositories import settings_repo, audit_repo

router = APIRouter(prefix="/api/settings", tags=["settings"])


class PDNSSettings(BaseModel):
    pdns_api_url: str
    pdns_api_key: str
    pdns_server_id: str


@router.get("/pdns")
async def get_pdns_settings(
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    cfg = await settings_repo.get_pdns_settings(db)
    return {
        "pdns_api_url": cfg.get("pdns_api_url", ""),
        "pdns_api_key": cfg.get("pdns_api_key", ""),
        "pdns_server_id": cfg.get("pdns_server_id", ""),
    }


@router.put("/pdns")
async def update_pdns_settings(
    body: PDNSSettings,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    if not body.pdns_api_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="API URL must start with http:// or https://")
    if not body.pdns_api_key:
        raise HTTPException(status_code=400, detail="API key cannot be empty")
    if not body.pdns_server_id:
        raise HTTPException(status_code=400, detail="Server ID cannot be empty")

    await settings_repo.upsert_setting(db, "pdns_api_url", body.pdns_api_url)
    await settings_repo.upsert_setting(db, "pdns_api_key", body.pdns_api_key)
    await settings_repo.upsert_setting(db, "pdns_server_id", body.pdns_server_id)

    await pdns.reconfigure(
        api_url=body.pdns_api_url,
        api_key=body.pdns_api_key,
        server_id=body.pdns_server_id,
    )

    await audit_repo.log_action(
        db, user.id, user.username, "settings.pdns.update",
        detail={"pdns_api_url": body.pdns_api_url, "pdns_server_id": body.pdns_server_id},
    )

    return {"status": "ok"}


@router.post("/pdns/test")
async def test_pdns_connection(
    body: PDNSSettings,
    user: User = Depends(require_admin),
):
    if not body.pdns_api_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="API URL must start with http:// or https://")

    import httpx
    url = f"{body.pdns_api_url.rstrip('/')}/api/v1/servers/{body.pdns_server_id}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers={"X-API-Key": body.pdns_api_key})
        if resp.status_code == 200:
            return {"status": "ok", "detail": f"Connected to {resp.json().get('type', 'PowerDNS')}"}
        elif resp.status_code == 401:
            raise HTTPException(status_code=401, detail="Authentication failed — check API key")
        elif resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Server ID not found — check server ID")
        else:
            raise HTTPException(status_code=resp.status_code, detail=f"PowerDNS returned {resp.status_code}")
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Cannot reach PowerDNS — check API URL")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Connection timed out — check API URL")
