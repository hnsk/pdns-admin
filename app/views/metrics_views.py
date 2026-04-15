from pathlib import Path

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.repositories import pdns_server_repo

router = APIRouter(tags=["metrics-views"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/metrics", response_class=HTMLResponse)
async def metrics_overview(
    request: Request,
    user: User = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    servers = [s for s in await pdns_server_repo.list_servers(db) if s["is_active"]]
    return templates.TemplateResponse(request, "metrics/overview.html", {
        "user": user,
        "active_page": "metrics",
        "servers": servers,
    })


@router.get("/metrics/{server_db_id}", response_class=HTMLResponse)
async def metrics_detail(
    server_db_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    srv = await pdns_server_repo.get_server(db, server_db_id)
    if srv is None:
        raise HTTPException(404, "Server not found")
    return templates.TemplateResponse(request, "metrics/detail.html", {
        "user": user,
        "active_page": "metrics",
        "server": srv,
    })
