import asyncio
from urllib.parse import urlparse

import aiosqlite
import dns.asyncquery
import dns.asyncresolver
import dns.exception
import dns.name
import dns.zone
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.repositories import pdns_server_repo, zone_assignment_repo

router = APIRouter(prefix="/api/tools", tags=["tools"])


def _host_from_server(server_row) -> str:
    return urlparse(server_row["api_url"]).hostname


async def _do_axfr(zone_id: str, host: str) -> dict:
    z = dns.zone.Zone(dns.name.from_text(zone_id))
    await dns.asyncquery.inbound_xfr(host, z)
    records = []
    for name, node in sorted(z.nodes.items()):
        fqdn = str(name.derelativize(z.origin))
        for rdataset in node.rdatasets:
            rtype = dns.rdatatype.to_text(rdataset.rdtype)
            for rdata in rdataset:
                records.append({
                    "name": fqdn,
                    "ttl": rdataset.ttl,
                    "rtype": rtype,
                    "rdata": rdata.to_text(origin=z.origin, relativize=False),
                })
    text_lines = [
        f"; <<>> DiG <<>> {zone_id} AXFR @{host}",
        ";; global options: +cmd",
    ]
    for rec in records:
        text_lines.append(f"{rec['name']}\t{rec['ttl']}\tIN\t{rec['rtype']}\t{rec['rdata']}")
    return {"text": "\n".join(text_lines), "records": records}


async def _do_lookup(name: str, rtype: str, host: str) -> list[dict]:
    resolver = dns.asyncresolver.Resolver(configure=False)
    resolver.nameservers = [host]
    resolver.port = 53
    resolver.lifetime = 5
    answer = await resolver.resolve(name, rtype)
    return [
        {"name": str(answer.qname), "ttl": answer.rrset.ttl, "rtype": rtype, "rdata": str(r)}
        for r in answer
    ]


async def _run_axfr(zone_id: str, server_id: int | None, server_name: str, host: str) -> dict:
    try:
        result = await _do_axfr(zone_id, host)
        return {"server_id": server_id, "server_name": server_name, "text": result["text"], "records": result["records"], "error": None}
    except Exception as e:
        return {"server_id": server_id, "server_name": server_name, "text": None, "records": [], "error": str(e)}


async def _run_lookup(name: str, rtype: str, server_id: int | None, server_name: str, host: str) -> dict:
    try:
        answers = await _do_lookup(name, rtype, host)
        return {"server_id": server_id, "server_name": server_name, "answers": answers, "error": None}
    except dns.resolver.NXDOMAIN:
        return {"server_id": server_id, "server_name": server_name, "answers": [], "error": "NXDOMAIN"}
    except dns.resolver.NoAnswer:
        return {"server_id": server_id, "server_name": server_name, "answers": [], "error": "No answer"}
    except dns.exception.Timeout:
        return {"server_id": server_id, "server_name": server_name, "answers": [], "error": "Timeout"}
    except Exception as e:
        return {"server_id": server_id, "server_name": server_name, "answers": [], "error": str(e)}


class AXFRRequest(BaseModel):
    zone_id: str
    server_ids: list[int] = []
    custom_hosts: list[str] = []


class LookupRequest(BaseModel):
    name: str
    rtype: str
    server_ids: list[int] = []
    custom_hosts: list[str] = []


@router.post("/axfr")
async def axfr_endpoint(
    body: AXFRRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    all_servers = {s["id"]: s for s in await pdns_server_repo.list_servers(db) if s["is_active"]}
    servers = [all_servers[sid] for sid in body.server_ids if sid in all_servers]
    custom_hosts = [h.strip() for h in body.custom_hosts if h.strip()]
    if not servers and not custom_hosts:
        raise HTTPException(status_code=400, detail="No valid active servers selected")

    # Operator: restrict to assigned zones
    if user.role != "admin":
        assignments = await zone_assignment_repo.get_user_zone_assignments(db, user.id)
        allowed = {a["zone_name"] for a in assignments}
        if body.zone_id not in allowed:
            raise HTTPException(status_code=403, detail="No access to this zone")

    tasks = [_run_axfr(body.zone_id, srv["id"], srv["name"], _host_from_server(srv)) for srv in servers]
    tasks += [_run_axfr(body.zone_id, None, h, h) for h in custom_hosts]
    results = await asyncio.gather(*tasks)

    accept = request.headers.get("accept", "")
    if "text/plain" in accept:
        lines = []
        for r in results:
            lines.append(f"=== {r['server_name']} ===")
            lines.append(r["text"] if r["text"] is not None else f"ERROR: {r['error']}")
            lines.append("")
        return PlainTextResponse("\n".join(lines))

    return {"results": list(results)}


@router.post("/lookup")
async def lookup_endpoint(
    body: LookupRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    all_servers = {s["id"]: s for s in await pdns_server_repo.list_servers(db) if s["is_active"]}
    servers = [all_servers[sid] for sid in body.server_ids if sid in all_servers]
    custom_hosts = [h.strip() for h in body.custom_hosts if h.strip()]
    if not servers and not custom_hosts:
        raise HTTPException(status_code=400, detail="No valid active servers selected")

    tasks = [_run_lookup(body.name, body.rtype, srv["id"], srv["name"], _host_from_server(srv)) for srv in servers]
    tasks += [_run_lookup(body.name, body.rtype, None, h, h) for h in custom_hosts]
    results = await asyncio.gather(*tasks)

    accept = request.headers.get("accept", "")
    if "text/plain" in accept:
        lines = []
        for r in results:
            lines.append(f"=== {r['server_name']} ===")
            if r["error"]:
                lines.append(f"ERROR: {r['error']}")
            else:
                for a in r["answers"]:
                    lines.append(f"{a['name']}\t{a['ttl']}\tIN\t{a['rtype']}\t{a['rdata']}")
            lines.append("")
        return PlainTextResponse("\n".join(lines))

    return {"results": list(results)}
