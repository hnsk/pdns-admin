from pathlib import Path

import aiosqlite
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.repositories import pdns_server_repo, zone_assignment_repo
from app.views.zone_views import RECORD_TYPES

router = APIRouter(tags=["tools-views"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/tools", response_class=HTMLResponse)
async def tools_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    active_servers = [s for s in await pdns_server_repo.list_servers(db) if s["is_active"]]
    # Strip api_key from server rows passed to template
    safe_servers = [{k: v for k, v in s.items() if k != "api_key"} for s in active_servers]

    if user.role == "admin":
        rows = await db.execute_fetchall("SELECT DISTINCT zone_name FROM zone_server_map ORDER BY zone_name")
        accessible_zones = [r[0] for r in rows]
    else:
        assignments = await zone_assignment_repo.get_user_zone_assignments(db, user.id)
        accessible_zones = sorted({a["zone_name"] for a in assignments})
        assigned_server_ids = {a["pdns_server_id"] for a in assignments if a["pdns_server_id"] is not None}
        safe_servers = [s for s in safe_servers if s["id"] in assigned_server_ids]

    return templates.TemplateResponse(request, "tools.html", context={
        "user": user,
        "active_page": "tools",
        "active_servers": safe_servers,
        "record_types": RECORD_TYPES,
        "accessible_zones": accessible_zones,
    })
