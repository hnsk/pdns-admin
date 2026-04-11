import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import aiosqlite

from app.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.pdns_client import pdns, PDNSError
from app.repositories import zone_assignment_repo, zone_template_repo

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
    try:
        zones = await pdns.list_zones()
    except PDNSError:
        zones = []

    if user.role != "admin":
        allowed = set(await zone_assignment_repo.get_user_zones(db, user.id))
        zones = [z for z in zones if z.get("id") in allowed or z.get("name") in allowed]

    async def _add_rrset_count(zone: dict) -> dict:
        try:
            full = await pdns.get_zone(zone["id"])
            zone["rrset_count"] = len(full.get("rrsets", []))
        except PDNSError:
            pass
        return zone

    if zones:
        zones = list(await asyncio.gather(*[_add_rrset_count(z) for z in zones]))

    zone_templates = await zone_template_repo.list_templates(db)
    return templates.TemplateResponse(request, "zones/list.html", context={
        "user": user,
        "active_page": "zones",
        "zones": zones,
        "zone_templates": zone_templates,
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

    try:
        zone = await pdns.get_zone(zone_id)
    except PDNSError:
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

    try:
        export_data = await pdns.export_zone(zone_id)
    except PDNSError:
        export_data = "Failed to export zone"

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
):
    if user.role != "admin":
        return RedirectResponse(url="/zones", status_code=302)

    try:
        zone = await pdns.get_zone(zone_id, rrsets=False)
        dnssec_enabled = zone.get("dnssec", False)
    except PDNSError:
        return RedirectResponse(url="/zones", status_code=302)

    keys = []
    if dnssec_enabled:
        try:
            keys = await pdns.list_cryptokeys(zone_id)
        except PDNSError:
            pass

    return templates.TemplateResponse(request, "dnssec/keys.html", context={
        "user": user,
        "active_page": "zones",
        "zone_id": zone_id,
        "dnssec_enabled": dnssec_enabled,
        "keys": keys,
    })
