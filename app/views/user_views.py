from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import aiosqlite

from app.auth import require_admin, get_current_user
from app.database import get_db
from app.models.user import User
from app.pdns_client import PDNSError, registry
from app.repositories import pdns_server_repo, user_repo, zone_assignment_repo, settings_repo

router = APIRouter(tags=["user-views"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/users", response_class=HTMLResponse)
async def users_list(
    request: Request,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    users = await user_repo.list_users(db)
    users_with_zones = []
    for u in users:
        zones = await zone_assignment_repo.get_user_zones(db, u.id)
        users_with_zones.append({**u.model_dump(), "zone_count": len(zones)})

    return templates.TemplateResponse(request, "users/list.html", context={
        "user": user,
        "active_page": "users",
        "users": users_with_zones,
    })


@router.get("/users/{user_id}", response_class=HTMLResponse)
async def user_detail(
    user_id: int,
    request: Request,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    target = await user_repo.get_user_by_id(db, user_id)
    if not target:
        return RedirectResponse(url="/users", status_code=302)

    raw_assignments = await zone_assignment_repo.get_user_zone_assignments(db, user_id)

    active_servers = [s for s in await pdns_server_repo.list_servers(db) if s["is_active"]]
    server_name_map = {s["id"]: s["name"] for s in active_servers}

    assigned_zones = [
        {
            "zone_name": a["zone_name"],
            "pdns_server_id": a["pdns_server_id"],
            "server_name": server_name_map.get(a["pdns_server_id"], "Unknown") if a["pdns_server_id"] else "Any",
        }
        for a in raw_assignments
    ]

    servers_with_zones = []
    for srv in active_servers:
        try:
            zones = await registry.get(srv["id"]).list_zones()
            zone_names = sorted(z.get("name") or z.get("id", "") for z in zones)
            servers_with_zones.append({
                "id": srv["id"],
                "name": srv["name"],
                "zones": zone_names,
            })
        except (PDNSError, RuntimeError):
            pass

    return templates.TemplateResponse(request, "users/detail.html", context={
        "user": user,
        "active_page": "users",
        "target_user": target,
        "assigned_zones": assigned_zones,
        "servers_with_zones": servers_with_zones,
    })


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    raw_ttl = await settings_repo.get_setting(db, "default_record_ttl")
    global_default_ttl = int(raw_ttl) if raw_ttl is not None else 60
    return templates.TemplateResponse(request, "profile.html", context={
        "user": user,
        "active_page": "profile",
        "global_default_ttl": global_default_ttl,
    })


@router.get("/audit", response_class=HTMLResponse)
async def audit_page(request: Request, user: User = Depends(require_admin)):
    return templates.TemplateResponse(request, "audit.html", context={
        "user": user,
        "active_page": "audit",
    })
