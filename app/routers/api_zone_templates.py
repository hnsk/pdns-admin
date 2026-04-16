from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import aiosqlite

from app.auth import require_admin
from app.database import get_db
from app.models.user import User
from app.repositories import audit_repo, zone_template_repo

router = APIRouter(prefix="/api/zone-templates", tags=["zone-templates"])


class ZoneTemplateCreate(BaseModel):
    name: str
    nameservers: list[str] = []
    soa_mname: str = ""
    soa_rname: str = ""
    soa_refresh: int = 3600
    soa_retry: int = 900
    soa_expire: int = 604800
    soa_ttl: int = 300
    is_default: bool = False


@router.get("")
async def list_templates(
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    return await zone_template_repo.list_templates(db)


@router.post("", status_code=201)
async def create_template(
    body: ZoneTemplateCreate,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Template name cannot be empty")
    try:
        tmpl = await zone_template_repo.create_template(
            db,
            name=body.name.strip(),
            nameservers=body.nameservers,
            soa_mname=body.soa_mname,
            soa_rname=body.soa_rname,
            soa_refresh=body.soa_refresh,
            soa_retry=body.soa_retry,
            soa_expire=body.soa_expire,
            soa_ttl=body.soa_ttl,
            is_default=body.is_default,
        )
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(status_code=409, detail="A template with that name already exists")
        raise
    await audit_repo.log_action(db, user.id, user.username, "zone_template.create", detail={"name": body.name})
    return tmpl


@router.put("/{template_id}")
async def update_template(
    template_id: int,
    body: ZoneTemplateCreate,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    existing = await zone_template_repo.get_template(db, template_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Template not found")
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Template name cannot be empty")
    try:
        tmpl = await zone_template_repo.update_template(
            db,
            template_id=template_id,
            name=body.name.strip(),
            nameservers=body.nameservers,
            soa_mname=body.soa_mname,
            soa_rname=body.soa_rname,
            soa_refresh=body.soa_refresh,
            soa_retry=body.soa_retry,
            soa_expire=body.soa_expire,
            soa_ttl=body.soa_ttl,
            is_default=body.is_default,
        )
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(status_code=409, detail="A template with that name already exists")
        raise
    await audit_repo.log_action(db, user.id, user.username, "zone_template.update", detail={"id": template_id, "name": body.name})
    return tmpl


@router.post("/{template_id}/set-default")
async def set_default(
    template_id: int,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    existing = await zone_template_repo.get_template(db, template_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Template not found")
    await zone_template_repo.set_default(db, template_id)
    await audit_repo.log_action(db, user.id, user.username, "zone_template.set_default", detail={"id": template_id})
    return {"ok": True}


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: int,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    existing = await zone_template_repo.get_template(db, template_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Template not found")
    await zone_template_repo.delete_template(db, template_id)
    await audit_repo.log_action(db, user.id, user.username, "zone_template.delete", detail={"id": template_id})
