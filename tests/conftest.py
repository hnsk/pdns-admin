import pytest
import aiosqlite
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import get_db, run_migrations
from app.auth import get_current_user, require_admin, require_zone_access
from app.dependencies import get_pdns_for_zone
from app.pdns_client import PDNSClient
from app.repositories import user_repo, zone_assignment_repo

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await run_migrations(conn)
    yield conn
    await conn.close()


@pytest.fixture
async def admin_user(db):
    return await user_repo.create_user(db, "testadmin", "password", role="admin")


@pytest.fixture
async def operator_user(db):
    return await user_repo.create_user(db, "testop", "password", role="operator")


@pytest.fixture
async def assigned_operator(db, operator_user):
    await zone_assignment_repo.assign_zone(db, operator_user.id, "example.com.")
    return operator_user


@pytest.fixture
def mock_pdns():
    client = MagicMock(spec=PDNSClient)
    client.get_zone = AsyncMock(return_value={"id": "example.com.", "name": "example.com.", "rrsets": []})
    client.create_zone = AsyncMock(return_value={"id": "example.com.", "name": "example.com."})
    client.delete_zone = AsyncMock(return_value=None)
    client.update_zone = AsyncMock(return_value=None)
    client.patch_rrsets = AsyncMock(return_value=None)
    client.export_zone = AsyncMock(return_value="; zone data\nexample.com. 300 IN SOA ns1 admin 1 3600 900 604800 300")
    client.list_zones = AsyncMock(return_value=[])
    return client


def _make_overrides(db, user, mock_pdns=None):
    async def override_get_db():
        return db

    async def override_get_user():
        return user

    async def override_require_admin():
        if user.role != "admin":
            from fastapi import HTTPException
            raise HTTPException(403, "Admin access required")
        return user

    async def override_require_zone_access():
        return user

    overrides = {
        get_db: override_get_db,
        get_current_user: override_get_user,
        require_admin: override_require_admin,
        require_zone_access: override_require_zone_access,
    }
    if mock_pdns is not None:
        async def override_pdns():
            return mock_pdns
        overrides[get_pdns_for_zone] = override_pdns
    return overrides


@pytest.fixture
async def client_as_admin(db, admin_user, mock_pdns):
    app.dependency_overrides.update(_make_overrides(db, admin_user, mock_pdns))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, mock_pdns
    app.dependency_overrides.clear()


@pytest.fixture
async def client_as_operator(db, assigned_operator, mock_pdns):
    app.dependency_overrides.update(_make_overrides(db, assigned_operator, mock_pdns))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, mock_pdns
    app.dependency_overrides.clear()


@pytest.fixture
async def client_unauthenticated(db):
    async def override_get_db():
        return db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
