from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import aiosqlite

from app.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.pdns_client import pdns, PDNSError
from app.repositories import audit_repo, user_repo, zone_assignment_repo

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

    try:
        zones = await pdns.list_zones()
        zone_count = len(zones)
        dnssec_count = sum(1 for z in zones if z.get("dnssec"))
    except PDNSError:
        zone_count = 0
        dnssec_count = 0

    user_count = 0
    recent_audit = []
    server_info = {}

    if user.role == "admin":
        users = await user_repo.list_users(db)
        user_count = len(users)
        recent_audit = await audit_repo.get_audit_log(db, limit=10)

    try:
        server_info = await pdns.get_server_info()
    except PDNSError:
        pass

    return templates.TemplateResponse(request, "dashboard.html", context={
        "user": user,
        "active_page": "dashboard",
        "zone_count": zone_count,
        "user_count": user_count,
        "dnssec_count": dnssec_count,
        "recent_audit": recent_audit,
        "server_info": server_info,
    })
