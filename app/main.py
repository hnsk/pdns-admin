from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import init_db, close_db
from app.pdns_client import pdns
from app.repositories.user_repo import ensure_admin_exists
from app.repositories.settings_repo import seed_defaults, get_pdns_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = await init_db()
    await ensure_admin_exists(db, settings.default_admin_password)
    await seed_defaults(db, {
        "pdns_api_url": settings.pdns_api_url,
        "pdns_api_key": settings.pdns_api_key,
        "pdns_server_id": settings.pdns_server_id,
    })
    pdns_cfg = await get_pdns_settings(db)
    await pdns.start(
        api_url=pdns_cfg["pdns_api_url"],
        api_key=pdns_cfg["pdns_api_key"],
        server_id=pdns_cfg["pdns_server_id"],
    )
    yield
    await pdns.close()
    await close_db()


app = FastAPI(title="PowerAdmin", version="1.0.0", lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

# Static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# API routers
from app.routers import api_auth, api_zones, api_dnssec, api_users, api_audit, api_settings, api_zone_templates  # noqa: E402

app.include_router(api_auth.router)
app.include_router(api_zones.router)
app.include_router(api_dnssec.router)
app.include_router(api_users.router)
app.include_router(api_audit.router)
app.include_router(api_settings.router)
app.include_router(api_zone_templates.router)

# View routers
from app.views import auth_views, zone_views, user_views, dashboard_views, settings_views  # noqa: E402

app.include_router(auth_views.router)
app.include_router(zone_views.router)
app.include_router(user_views.router)
app.include_router(dashboard_views.router)
app.include_router(settings_views.router)
