from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import aiosqlite

from app.auth import require_admin
from app.database import get_db
from app.models.user import User
from app.pdns_client import pdns, PDNSError
from app.repositories import user_repo, zone_assignment_repo

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

    assigned_zones = await zone_assignment_repo.get_user_zones(db, user_id)

    try:
        all_zones = await pdns.list_zones()
    except PDNSError:
        all_zones = []

    return templates.TemplateResponse(request, "users/detail.html", context={
        "user": user,
        "active_page": "users",
        "target_user": target,
        "assigned_zones": assigned_zones,
        "all_zones": all_zones,
    })


@router.get("/audit", response_class=HTMLResponse)
async def audit_page(request: Request, user: User = Depends(require_admin)):
    return templates.TemplateResponse(request, "audit.html", context={
        "user": user,
        "active_page": "audit",
    })
