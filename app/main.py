import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import init_db, close_db
from app.pdns_client import registry
from app.repositories.user_repo import ensure_admin_exists
from app.repositories import pdns_server_repo, settings_repo


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = await init_db()
    await settings_repo.seed_defaults(db, {"default_record_ttl": "60"})
    await ensure_admin_exists(db, settings.default_admin_password)
    for srv in await pdns_server_repo.list_servers(db):
        if srv["is_active"]:
            try:
                await registry.start_server(
                    srv["id"], srv["api_url"], srv["api_key"], srv["server_id"]
                )
            except Exception as exc:
                logging.warning("Failed to connect to %s: %s", srv["name"], exc)
    yield
    await registry.close_all()
    await close_db()


app = FastAPI(title="PowerAdmin", version="1.0.0", lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

# Static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# API routers
from app.routers import api_auth, api_zones, api_dnssec, api_users, api_audit, api_settings, api_zone_templates, api_pdns_servers, api_tools, api_metrics  # noqa: E402

app.include_router(api_auth.router)
app.include_router(api_zones.router)
app.include_router(api_dnssec.router)
app.include_router(api_users.router)
app.include_router(api_audit.router)
app.include_router(api_settings.router)
app.include_router(api_zone_templates.router)
app.include_router(api_pdns_servers.router)
app.include_router(api_tools.router)
app.include_router(api_metrics.router)

# View routers
from app.views import auth_views, zone_views, user_views, dashboard_views, settings_views, tools_views, metrics_views  # noqa: E402

app.include_router(auth_views.router)
app.include_router(zone_views.router)
app.include_router(user_views.router)
app.include_router(dashboard_views.router)
app.include_router(settings_views.router)
app.include_router(tools_views.router)
app.include_router(metrics_views.router)
