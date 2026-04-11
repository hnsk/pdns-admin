from fastapi import APIRouter, Depends, HTTPException

import aiosqlite

from app.auth import require_admin
from app.database import get_db
from app.dependencies import get_pdns_for_zone
from app.models.user import User
from app.models.zone import CryptoKeyCreate
from app.pdns_client import PDNSClient, PDNSError
from app.repositories import audit_repo

router = APIRouter(prefix="/api/zones", tags=["dnssec"])


def _handle_pdns_error(e: PDNSError):
    raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.get("/{zone_id}/cryptokeys")
async def list_cryptokeys(
    zone_id: str,
    user: User = Depends(require_admin),
    pdns_client: PDNSClient = Depends(get_pdns_for_zone),
):
    try:
        return await pdns_client.list_cryptokeys(zone_id)
    except PDNSError as e:
        _handle_pdns_error(e)


@router.post("/{zone_id}/cryptokeys", status_code=201)
async def create_cryptokey(
    zone_id: str,
    body: CryptoKeyCreate,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
    pdns_client: PDNSClient = Depends(get_pdns_for_zone),
):
    data = body.model_dump()
    try:
        key = await pdns_client.create_cryptokey(zone_id, data)
    except PDNSError as e:
        _handle_pdns_error(e)
    await audit_repo.log_action(
        db, user.id, user.username, "dnssec.key_create",
        zone_name=zone_id,
        detail={"keytype": body.keytype, "algorithm": body.algorithm},
    )
    return key


@router.get("/{zone_id}/cryptokeys/{key_id}")
async def get_cryptokey(
    zone_id: str,
    key_id: int,
    user: User = Depends(require_admin),
    pdns_client: PDNSClient = Depends(get_pdns_for_zone),
):
    try:
        return await pdns_client.get_cryptokey(zone_id, key_id)
    except PDNSError as e:
        _handle_pdns_error(e)


@router.put("/{zone_id}/cryptokeys/{key_id}")
async def toggle_cryptokey(
    zone_id: str,
    key_id: int,
    active: bool,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
    pdns_client: PDNSClient = Depends(get_pdns_for_zone),
):
    try:
        await pdns_client.toggle_cryptokey(zone_id, key_id, active)
    except PDNSError as e:
        _handle_pdns_error(e)
    await audit_repo.log_action(
        db, user.id, user.username,
        "dnssec.key_activate" if active else "dnssec.key_deactivate",
        zone_name=zone_id, detail={"key_id": key_id},
    )
    return {"ok": True}


@router.delete("/{zone_id}/cryptokeys/{key_id}")
async def delete_cryptokey(
    zone_id: str,
    key_id: int,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
    pdns_client: PDNSClient = Depends(get_pdns_for_zone),
):
    try:
        await pdns_client.delete_cryptokey(zone_id, key_id)
    except PDNSError as e:
        _handle_pdns_error(e)
    await audit_repo.log_action(
        db, user.id, user.username, "dnssec.key_delete",
        zone_name=zone_id, detail={"key_id": key_id},
    )
    return {"ok": True}


@router.post("/{zone_id}/dnssec/enable")
async def enable_dnssec(
    zone_id: str,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
    pdns_client: PDNSClient = Depends(get_pdns_for_zone),
):
    try:
        await pdns_client.update_zone(zone_id, {"dnssec": True})
    except PDNSError as e:
        _handle_pdns_error(e)
    await audit_repo.log_action(db, user.id, user.username, "dnssec.enable", zone_name=zone_id)
    return {"ok": True}


@router.post("/{zone_id}/dnssec/disable")
async def disable_dnssec(
    zone_id: str,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
    pdns_client: PDNSClient = Depends(get_pdns_for_zone),
):
    try:
        await pdns_client.update_zone(zone_id, {"dnssec": False})
    except PDNSError as e:
        _handle_pdns_error(e)
    await audit_repo.log_action(db, user.id, user.username, "dnssec.disable", zone_name=zone_id)
    return {"ok": True}
