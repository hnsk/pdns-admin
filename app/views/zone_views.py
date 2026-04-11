import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import aiosqlite

from app.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.pdns_client import PDNSError, registry
from app.repositories import pdns_server_repo, zone_assignment_repo, zone_template_repo

router = APIRouter(tags=["zone-views"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

# All RR types supported by PowerDNS
RECORD_TYPES = [
    "A", "AAAA", "AFSDB", "ALIAS", "APL", "CAA", "CDNSKEY", "CDS", "CERT",
    "CNAME", "CSYNC", "DHCID", "DLV", "DNAME", "DNSKEY", "DS", "EUI48",
    "EUI64", "HINFO", "HTTPS", "IPSECKEY", "KEY", "KX", "LOC", "LUA",
    "MAILA", "MAILB", "MB", "MG", "MINFO", "MR", "MX", "NAPTR", "NS",
    "NSEC", "NSEC3", "NSEC3PARAM", "NXT", "OPENPGPKEY", "PTR", "RP",
    "RRSIG", "SIG", "SMIMEA", "SOA", "SPF", "SRV", "SSHFP", "SVCB",
    "TKEY", "TLSA", "TSIG", "TXT", "URI", "WKS", "ZONEMD",
]


@router.get("/zones", response_class=HTMLResponse)
async def zones_list(request: Request, user: User = Depends(get_current_user), db: aiosqlite.Connection = Depends(get_db)):
    active_servers = [s for s in await pdns_server_repo.list_servers(db) if s["is_active"]]
    srv_by_id = {s["id"]: s for s in active_servers}

    # Fetch all zone->server mappings in one query
    mapping_rows = await db.execute_fetchall("SELECT zone_name, pdns_server_id FROM zone_server_map")
    zone_server_mapping = {row[0]: row[1] for row in mapping_rows}

    # Collect zones from all servers, dedup by zone name (first occurrence wins)
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
        except (PDNSError, RuntimeError):
            pass

    all_zones = list(seen.values())

    # Correct server attribution using zone_server_map
    for z in all_zones:
        name = z.get("name") or z.get("id")
        mapped_srv_id = zone_server_mapping.get(name)
        if mapped_srv_id and mapped_srv_id in srv_by_id:
            z["_server_id"] = mapped_srv_id
            z["_server_name"] = srv_by_id[mapped_srv_id]["name"]

    if user.role != "admin":
        allowed = set(await zone_assignment_repo.get_user_zones(db, user.id))
        all_zones = [z for z in all_zones if z.get("id") in allowed or z.get("name") in allowed]

    async def _add_rrset_count(zone: dict) -> dict:
        try:
            srv_id = zone.get("_server_id")
            client = registry.get(srv_id)
            full = await client.get_zone(zone["id"])
            zone["rrset_count"] = len(full.get("rrsets", []))
        except (PDNSError, RuntimeError):
            pass
        return zone

    if all_zones:
        all_zones = list(await asyncio.gather(*[_add_rrset_count(z) for z in all_zones]))

    zone_templates = await zone_template_repo.list_templates(db)
    pdns_servers = [
        {k: v for k, v in s.items() if k != "api_key"}
        for s in active_servers
    ]
    return templates.TemplateResponse(request, "zones/list.html", context={
        "user": user,
        "active_page": "zones",
        "zones": all_zones,
        "zone_templates": zone_templates,
        "pdns_servers": pdns_servers,
    })


@router.get("/zones/{zone_id}", response_class=HTMLResponse)
async def zone_detail(
    zone_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    if user.role != "admin":
        if not await zone_assignment_repo.user_has_zone_access(db, user.id, zone_id):
            return RedirectResponse(url="/zones", status_code=302)

    srv = await pdns_server_repo.get_server_for_zone_or_fallback(db, zone_id)
    if srv is None:
        return RedirectResponse(url="/zones", status_code=302)

    try:
        client = registry.get(srv["id"])
        zone = await client.get_zone(zone_id)
    except (PDNSError, RuntimeError):
        return RedirectResponse(url="/zones", status_code=302)

    return templates.TemplateResponse(request, "zones/detail.html", context={
        "user": user,
        "active_page": "zones",
        "zone": zone,
        "record_types": RECORD_TYPES,
    })


@router.get("/zones/{zone_id}/export", response_class=HTMLResponse)
async def zone_export_page(
    zone_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    if user.role != "admin":
        if not await zone_assignment_repo.user_has_zone_access(db, user.id, zone_id):
            return RedirectResponse(url="/zones", status_code=302)

    srv = await pdns_server_repo.get_server_for_zone_or_fallback(db, zone_id)
    export_data = "Failed to export zone"
    if srv is not None:
        try:
            client = registry.get(srv["id"])
            export_data = await client.export_zone(zone_id)
        except (PDNSError, RuntimeError):
            pass

    return templates.TemplateResponse(request, "zones/export.html", context={
        "user": user,
        "active_page": "zones",
        "zone_id": zone_id,
        "export_data": export_data,
    })


@router.get("/zones/{zone_id}/dnssec", response_class=HTMLResponse)
async def zone_dnssec_page(
    zone_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    if user.role != "admin":
        return RedirectResponse(url="/zones", status_code=302)

    srv = await pdns_server_repo.get_server_for_zone_or_fallback(db, zone_id)
    if srv is None:
        return RedirectResponse(url="/zones", status_code=302)

    try:
        client = registry.get(srv["id"])
        zone = await client.get_zone(zone_id, rrsets=False)
        dnssec_enabled = zone.get("dnssec", False)
    except (PDNSError, RuntimeError):
        return RedirectResponse(url="/zones", status_code=302)

    keys = []
    if dnssec_enabled:
        try:
            keys = await client.list_cryptokeys(zone_id)
        except PDNSError:
            pass

    return templates.TemplateResponse(request, "dnssec/keys.html", context={
        "user": user,
        "active_page": "zones",
        "zone_id": zone_id,
        "dnssec_enabled": dnssec_enabled,
        "keys": keys,
    })
