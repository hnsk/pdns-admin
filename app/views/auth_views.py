from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import aiosqlite

from app.auth import delete_session
from app.database import get_db

router = APIRouter(tags=["auth-views"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", context={"user": None, "error": None})


@router.get("/logout")
async def logout_page(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    session_id = request.cookies.get("session_id")
    if session_id:
        await delete_session(db, session_id)
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session_id")
    return response
