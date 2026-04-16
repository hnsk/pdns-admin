import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

import aiosqlite

from app.auth import get_current_user, require_admin, require_zone_access
from app.database import get_db
from app.dependencies import get_pdns_for_zone
from app.models.user import User
from app.models.zone import RRSet, ZoneCreate, ZoneUpdate
from app.pdns_client import PDNSClient, PDNSError, registry
from app.repositories import audit_repo, pdns_server_repo, zone_assignment_repo, zone_template_repo

router = APIRouter(prefix="/api/zones", tags=["zones"])
logger = logging.getLogger(__name__)

_QUOTED_TYPES = {"TXT", "SPF"}


def _ensure_quoted(content: str) -> str:
    """Wrap TXT/SPF content in double quotes if not already quoted."""
    content = content.strip()
    if content.startswith('"') and content.endswith('"') and len(content) >= 2:
        return content
    escaped = content.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _handle_pdns_error(e: PDNSError):
    raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.get("")
async def list_zones(
    user: User = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    active_servers = [s for s in await pdns_server_repo.list_servers(db) if s["is_active"]]
    seen: dict[str, dict] = {}
    for srv in active_servers:
        try:
            zones = await registry.get(srv["id"]).list_zones()
            for z in zones:
                name = z.get("name") or z.get("id")
                if name not in seen:
                    z["_server_id"] = srv["id"]
                    z["_server_name"] = srv["name"]
                    seen[name] = z
        except (PDNSError, RuntimeError) as e:
            logger.warning("Failed to list zones from server %s: %s", srv["name"], e)
    all_zones = list(seen.values())

    if user.role == "admin":
        return all_zones

    allowed = set(await zone_assignment_repo.get_user_zones(db, user.id))
    return [z for z in all_zones if z.get("id") in allowed or z.get("name") in allowed]


def _build_zone_rrsets(zone_fqdn: str, nameservers: list[str], soa_mname: str, soa_rname: str,
                       soa_refresh: int, soa_retry: int, soa_expire: int, soa_ttl: int) -> list[dict]:
    """Build SOA and NS rrsets for zone creation from template or manual values."""
    ns_list = [ns if ns.endswith(".") else ns + "." for ns in nameservers]
    soa_mname_fqdn = soa_mname if soa_mname.endswith(".") else soa_mname + "."
    soa_rname_fqdn = soa_rname if soa_rname.endswith(".") else soa_rname + "."
    soa_content = f"{soa_mname_fqdn} {soa_rname_fqdn} 0 {soa_refresh} {soa_retry} {soa_expire} {soa_ttl}"
    rrsets = [
        {
            "name": zone_fqdn,
            "type": "SOA",
            "ttl": soa_ttl,
            "changetype": "REPLACE",
            "records": [{"content": soa_content, "disabled": False}],
        },
    ]
    if ns_list:
        rrsets.append({
            "name": zone_fqdn,
            "type": "NS",
            "ttl": 3600,
            "changetype": "REPLACE",
            "records": [{"content": ns, "disabled": False} for ns in ns_list],
        })
    return rrsets


@router.post("", status_code=201)
async def create_zone(
    body: ZoneCreate,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    srv = await pdns_server_repo.get_server(db, body.server_id)
    if srv is None:
        raise HTTPException(400, "PowerDNS server not found")
    if not srv["is_active"]:
        raise HTTPException(400, "PowerDNS server is not active")

    try:
        pdns_client = registry.get(srv["id"])
    except RuntimeError:
        raise HTTPException(503, f"PowerDNS server '{srv['name']}' is not connected")

    nameservers = body.nameservers
    rrsets = None
    template_name = None

    if body.template_id is not None:
        tmpl = await zone_template_repo.get_template(db, body.template_id)
        if not tmpl:
            raise HTTPException(status_code=404, detail="Zone template not found")
        template_name = tmpl["name"]
        zone_fqdn = body.name if body.name.endswith(".") else body.name + "."
        rrsets = _build_zone_rrsets(
            zone_fqdn,
            nameservers=tmpl["nameservers"],
            soa_mname=tmpl["soa_mname"],
            soa_rname=tmpl["soa_rname"],
            soa_refresh=tmpl["soa_refresh"],
            soa_retry=tmpl["soa_retry"],
            soa_expire=tmpl["soa_expire"],
            soa_ttl=tmpl["soa_ttl"],
        )
        nameservers = []
    elif body.soa_mname and body.soa_rname:
        zone_fqdn = body.name if body.name.endswith(".") else body.name + "."
        rrsets = _build_zone_rrsets(
            zone_fqdn,
            nameservers=nameservers,
            soa_mname=body.soa_mname,
            soa_rname=body.soa_rname,
            soa_refresh=body.soa_refresh or 3600,
            soa_retry=body.soa_retry or 900,
            soa_expire=body.soa_expire or 604800,
            soa_ttl=body.soa_ttl or 300,
        )
        nameservers = []

    try:
        zone = await pdns_client.create_zone(
            name=body.name,
            kind=body.kind,
            nameservers=nameservers,
            masters=body.masters,
            rrsets=rrsets,
        )
    except PDNSError as e:
        _handle_pdns_error(e)

    zone_name = zone.get("name", body.name)
    await pdns_server_repo.map_zone_to_server(db, zone_name, srv["id"])

    detail: dict = {"kind": body.kind}
    if template_name:
        detail["template"] = template_name
    await audit_repo.log_action(
        db, user.id, user.username, "zone.create",
        zone_name=zone_name,
        detail=detail,
    )

    if body.kind.lower() == "slave":
        zone_id = zone.get("id", body.name)
        try:
            await pdns_client.axfr_retrieve(zone_id)
            await audit_repo.log_action(
                db, user.id, user.username, "zone.axfr_retrieve",
                zone_name=zone_id,
            )
        except PDNSError:
            pass  # non-fatal: zone created, AXFR can be triggered manually

    return zone


@router.get("/{zone_id}")
async def get_zone(
    zone_id: str,
    user: User = Depends(require_zone_access),
    pdns_client: PDNSClient = Depends(get_pdns_for_zone),
):
    try:
        return await pdns_client.get_zone(zone_id)
    except PDNSError as e:
        _handle_pdns_error(e)


@router.put("/{zone_id}")
async def update_zone(
    zone_id: str,
    body: ZoneUpdate,
    user: User = Depends(require_zone_access),
    db: aiosqlite.Connection = Depends(get_db),
    pdns_client: PDNSClient = Depends(get_pdns_for_zone),
):
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    if user.role != "admin" and "kind" in data:
        raise HTTPException(status_code=403, detail="Only admins can change zone type")
    try:
        await pdns_client.update_zone(zone_id, data)
    except PDNSError as e:
        _handle_pdns_error(e)

    await audit_repo.log_action(db, user.id, user.username, "zone.update", zone_name=zone_id, detail=data)
    return {"ok": True}


@router.delete("/{zone_id}")
async def delete_zone(
    zone_id: str,
    server_id: int | None = Query(default=None),
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
    pdns_client: PDNSClient = Depends(get_pdns_for_zone),
):
    try:
        await pdns_client.delete_zone(zone_id)
    except PDNSError as e:
        _handle_pdns_error(e)

    if server_id is not None:
        await pdns_server_repo.unmap_zone_from_server(db, zone_id, server_id)
        remaining = await pdns_server_repo.count_zone_servers(db, zone_id)
        if remaining == 0:
            await zone_assignment_repo.delete_zone_assignments(db, zone_id)
    else:
        await zone_assignment_repo.delete_zone_assignments(db, zone_id)
        await pdns_server_repo.unmap_zone(db, zone_id)

    await audit_repo.log_action(
        db, user.id, user.username, "zone.delete",
        zone_name=zone_id,
        detail={"server_id": server_id},
    )
    return {"ok": True}


@router.patch("/{zone_id}/rrsets")
async def patch_rrsets(
    zone_id: str,
    rrsets: list[RRSet],
    user: User = Depends(require_zone_access),
    db: aiosqlite.Connection = Depends(get_db),
    pdns_client: PDNSClient = Depends(get_pdns_for_zone),
):
    for rs in rrsets:
        if rs.type in _QUOTED_TYPES:
            for record in rs.records:
                record.content = _ensure_quoted(record.content)
    payload = [rs.model_dump() for rs in rrsets]
    try:
        await pdns_client.patch_rrsets(zone_id, payload)
    except PDNSError as e:
        _handle_pdns_error(e)

    for rs in rrsets:
        await audit_repo.log_action(
            db, user.id, user.username,
            f"record.{rs.changetype.lower()}",
            zone_name=zone_id,
            detail={"name": rs.name, "type": rs.type, "ttl": rs.ttl, "records": [r.model_dump() for r in rs.records]},
        )
    return {"ok": True}


@router.get("/{zone_id}/export")
async def export_zone(
    zone_id: str,
    user: User = Depends(require_zone_access),
    pdns_client: PDNSClient = Depends(get_pdns_for_zone),
):
    try:
        text = await pdns_client.export_zone(zone_id)
    except PDNSError as e:
        _handle_pdns_error(e)
    return PlainTextResponse(text)


@router.put("/{zone_id}/rectify")
async def rectify_zone(
    zone_id: str,
    user: User = Depends(require_zone_access),
    db: aiosqlite.Connection = Depends(get_db),
    pdns_client: PDNSClient = Depends(get_pdns_for_zone),
):
    try:
        await pdns_client.rectify_zone(zone_id)
    except PDNSError as e:
        _handle_pdns_error(e)
    await audit_repo.log_action(db, user.id, user.username, "zone.rectify", zone_name=zone_id)
    return {"ok": True}


@router.put("/{zone_id}/notify")
async def notify_zone(
    zone_id: str,
    user: User = Depends(require_zone_access),
    db: aiosqlite.Connection = Depends(get_db),
    pdns_client: PDNSClient = Depends(get_pdns_for_zone),
):
    try:
        await pdns_client.notify_zone(zone_id)
    except PDNSError as e:
        _handle_pdns_error(e)
    await audit_repo.log_action(db, user.id, user.username, "zone.notify", zone_name=zone_id)
    return {"ok": True}


@router.put("/{zone_id}/axfr-retrieve")
async def axfr_retrieve(
    zone_id: str,
    user: User = Depends(require_zone_access),
    db: aiosqlite.Connection = Depends(get_db),
    pdns_client: PDNSClient = Depends(get_pdns_for_zone),
):
    try:
        await pdns_client.axfr_retrieve(zone_id)
    except PDNSError as e:
        _handle_pdns_error(e)
    await audit_repo.log_action(db, user.id, user.username, "zone.axfr_retrieve", zone_name=zone_id)
    return {"ok": True}


@router.get("/{zone_id}/metadata")
async def list_metadata(
    zone_id: str,
    user: User = Depends(require_zone_access),
    pdns_client: PDNSClient = Depends(get_pdns_for_zone),
):
    try:
        return await pdns_client.list_metadata(zone_id)
    except PDNSError as e:
        _handle_pdns_error(e)


@router.put("/{zone_id}/metadata/{kind}")
async def set_metadata(
    zone_id: str,
    kind: str,
    value: list[str],
    user: User = Depends(require_zone_access),
    db: aiosqlite.Connection = Depends(get_db),
    pdns_client: PDNSClient = Depends(get_pdns_for_zone),
):
    try:
        await pdns_client.set_metadata(zone_id, kind, value)
    except PDNSError as e:
        _handle_pdns_error(e)
    await audit_repo.log_action(db, user.id, user.username, "metadata.set", zone_name=zone_id, detail={"kind": kind, "value": value})
    return {"ok": True}
