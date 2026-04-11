from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import aiosqlite

from app.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.pdns_client import PDNSError, registry
from app.repositories import audit_repo, pdns_server_repo, user_repo

router = APIRouter(tags=["dashboard-views"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    # Check auth manually for redirect
    session_id = request.cookies.get("session_id")
    if not session_id:
        return RedirectResponse(url="/login", status_code=302)

    from app.auth import get_session_user
    user = await get_session_user(db, session_id)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if user.role == "operator":
        return RedirectResponse(url="/zones", status_code=302)

    active_servers = [s for s in await pdns_server_repo.list_servers(db) if s["is_active"]]

    zone_count = 0
    dnssec_count = 0
    server_infos = []

    for srv in active_servers:
        entry = {"name": srv["name"], "connected": False, "zone_count": 0, "dnssec_count": 0, "server_info": {}}
        try:
            client = registry.get(srv["id"])
            zones = await client.list_zones()
            entry["zone_count"] = len(zones)
            entry["dnssec_count"] = sum(1 for z in zones if z.get("dnssec"))
            zone_count += entry["zone_count"]
            dnssec_count += entry["dnssec_count"]
            entry["server_info"] = await client.get_server_info()
            entry["connected"] = True
        except (PDNSError, RuntimeError):
            pass
        server_infos.append(entry)

    user_count = 0
    recent_audit = []

    if user.role == "admin":
        users = await user_repo.list_users(db)
        user_count = len(users)
        recent_audit = await audit_repo.get_audit_log(db, limit=10)

    return templates.TemplateResponse(request, "dashboard.html", context={
        "user": user,
        "active_page": "dashboard",
        "zone_count": zone_count,
        "user_count": user_count,
        "dnssec_count": dnssec_count,
        "recent_audit": recent_audit,
        "server_infos": server_infos,
    })
