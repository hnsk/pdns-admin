from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import aiosqlite

from app.auth import require_admin
from app.database import get_db
from app.models.user import User
from app.repositories import settings_repo, zone_template_repo

router = APIRouter(tags=["settings-views"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    user: User = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    cfg = await settings_repo.get_pdns_settings(db)
    zone_templates = await zone_template_repo.list_templates(db)
    return templates.TemplateResponse(request, "settings.html", context={
        "user": user,
        "active_page": "settings",
        "pdns_api_url": cfg.get("pdns_api_url", ""),
        "pdns_api_key": cfg.get("pdns_api_key", ""),
        "pdns_server_id": cfg.get("pdns_server_id", ""),
        "zone_templates": zone_templates,
    })
