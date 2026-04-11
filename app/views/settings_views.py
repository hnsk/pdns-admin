from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import aiosqlite

from app.auth import require_admin
from app.database import get_db
from app.models.user import User
from app.repositories import pdns_server_repo, zone_template_repo, settings_repo

router = APIRouter(tags=["settings-views"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    servers = await pdns_server_repo.list_servers(db)
    pdns_servers = [{k: v for k, v in s.items() if k != "api_key"} for s in servers]
    zone_templates = await zone_template_repo.list_templates(db)
    raw_ttl = await settings_repo.get_setting(db, "default_record_ttl")
    default_record_ttl = int(raw_ttl) if raw_ttl is not None else 60
    return templates.TemplateResponse(request, "settings.html", context={
        "user": user,
        "active_page": "settings",
        "pdns_servers": pdns_servers,
        "zone_templates": zone_templates,
        "default_record_ttl": default_record_ttl,
    })
