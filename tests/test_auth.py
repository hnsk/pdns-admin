import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import get_db
from app.auth import get_current_user
from app.dependencies import get_pdns_for_zone


async def test_unauthenticated_get_zones(client_unauthenticated):
    response = await client_unauthenticated.get("/api/zones")
    assert response.status_code == 401


async def test_unauthenticated_patch_rrsets(client_unauthenticated):
    response = await client_unauthenticated.patch("/api/zones/example.com./rrsets", json=[])
    assert response.status_code == 401


async def test_operator_post_zone_forbidden(client_as_operator):
    ac, _ = client_as_operator
    response = await ac.post("/api/zones", json={"name": "x.com.", "server_id": 1})
    assert response.status_code == 403


async def test_operator_delete_zone_forbidden(client_as_operator):
    ac, _ = client_as_operator
    response = await ac.delete("/api/zones/example.com.")
    assert response.status_code == 403


async def test_unassigned_operator_zone_access_real_check(db, operator_user, mock_pdns):
    """Real require_zone_access runs: operator not assigned to zone → 403."""
    async def override_db():
        return db

    async def override_user():
        return operator_user

    async def override_pdns():
        return mock_pdns

    # Override get_current_user and get_pdns_for_zone, but NOT require_zone_access.
    # require_zone_access will query the real (in-memory) DB and find no assignment.
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_pdns_for_zone] = override_pdns

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/zones/example.com.")

    app.dependency_overrides.clear()
    assert response.status_code == 403
