import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.pdns_client import PDNSError
from app.repositories import pdns_server_repo


ZONE_ID = "example.com."


# --- GET /api/zones/ ---

async def test_list_zones_no_servers(client_as_admin):
    ac, mock_pdns = client_as_admin
    response = await ac.get("/api/zones")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_zones_admin_sees_all(db, client_as_admin):
    ac, mock_pdns = client_as_admin
    srv = await pdns_server_repo.create_server(db, "test", "http://localhost", "key", "localhost")
    mock_pdns.list_zones = AsyncMock(return_value=[
        {"id": "example.com.", "name": "example.com."},
        {"id": "other.com.", "name": "other.com."},
    ])
    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_pdns
    with patch("app.routers.api_zones.registry", mock_registry):
        response = await ac.get("/api/zones")
    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_list_zones_operator_sees_assigned_only(db, client_as_operator):
    ac, mock_pdns = client_as_operator
    srv = await pdns_server_repo.create_server(db, "test", "http://localhost", "key", "localhost")
    # PDNS returns 2 zones; operator is only assigned to example.com.
    mock_pdns.list_zones = AsyncMock(return_value=[
        {"id": "example.com.", "name": "example.com."},
        {"id": "other.com.", "name": "other.com."},
    ])
    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_pdns
    with patch("app.routers.api_zones.registry", mock_registry):
        response = await ac.get("/api/zones")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "example.com."


# --- POST /api/zones/ ---

async def test_create_zone_admin(db, client_as_admin):
    ac, mock_pdns = client_as_admin
    srv = await pdns_server_repo.create_server(db, "test", "http://localhost", "key", "localhost")
    mock_pdns.create_zone = AsyncMock(return_value={"id": "newzone.com.", "name": "newzone.com."})
    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_pdns
    with patch("app.routers.api_zones.registry", mock_registry):
        response = await ac.post("/api/zones", json={"name": "newzone.com.", "server_id": srv["id"]})
    assert response.status_code == 201
    mock_pdns.create_zone.assert_called_once()


async def test_create_zone_operator_forbidden(client_as_operator):
    ac, _ = client_as_operator
    response = await ac.post("/api/zones", json={"name": "newzone.com.", "server_id": 1})
    assert response.status_code == 403


async def test_create_zone_unknown_server(client_as_admin):
    ac, _ = client_as_admin
    response = await ac.post("/api/zones", json={"name": "newzone.com.", "server_id": 9999})
    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()


async def test_create_zone_inactive_server(db, client_as_admin):
    ac, _ = client_as_admin
    srv = await pdns_server_repo.create_server(db, "inactive", "http://localhost", "key", "localhost")
    await pdns_server_repo.update_server(
        db, srv["id"], srv["name"], srv["api_url"], srv["api_key"], srv["server_id"], False
    )
    response = await ac.post("/api/zones", json={"name": "newzone.com.", "server_id": srv["id"]})
    assert response.status_code == 400
    assert "not active" in response.json()["detail"].lower()


# --- GET /api/zones/{zone_id} ---

async def test_get_zone_happy(client_as_admin):
    ac, mock_pdns = client_as_admin
    response = await ac.get(f"/api/zones/{ZONE_ID}")
    assert response.status_code == 200
    mock_pdns.get_zone.assert_called_once_with(ZONE_ID)


async def test_get_zone_pdns_error(client_as_admin):
    ac, mock_pdns = client_as_admin
    mock_pdns.get_zone.side_effect = PDNSError(404, "Not found")
    response = await ac.get("/api/zones/notexist.com.")
    assert response.status_code == 404


# --- PUT /api/zones/{zone_id} ---

async def test_update_zone_empty_body(client_as_admin):
    ac, _ = client_as_admin
    response = await ac.put(f"/api/zones/{ZONE_ID}", json={})
    assert response.status_code == 400
    assert "No fields to update" in response.json()["detail"]


async def test_update_zone_operator_change_kind_forbidden(client_as_operator):
    ac, _ = client_as_operator
    response = await ac.put(f"/api/zones/{ZONE_ID}", json={"kind": "Slave"})
    assert response.status_code == 403


async def test_update_zone_admin_success(client_as_admin):
    ac, mock_pdns = client_as_admin
    response = await ac.put(f"/api/zones/{ZONE_ID}", json={"kind": "Slave"})
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    mock_pdns.update_zone.assert_called_once()


async def test_update_zone_pdns_error_propagated(client_as_admin):
    ac, mock_pdns = client_as_admin
    mock_pdns.update_zone.side_effect = PDNSError(422, "Validation error")
    response = await ac.put(f"/api/zones/{ZONE_ID}", json={"kind": "Slave"})
    assert response.status_code == 422


# --- DELETE /api/zones/{zone_id} ---

async def test_delete_zone_operator_forbidden(client_as_operator):
    ac, _ = client_as_operator
    response = await ac.delete(f"/api/zones/{ZONE_ID}")
    assert response.status_code == 403


async def test_delete_zone_admin_success(client_as_admin):
    ac, mock_pdns = client_as_admin
    response = await ac.delete(f"/api/zones/{ZONE_ID}")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    mock_pdns.delete_zone.assert_called_once_with(ZONE_ID)


# --- GET /api/zones/{zone_id}/export ---

async def test_export_zone(client_as_admin):
    ac, mock_pdns = client_as_admin
    response = await ac.get(f"/api/zones/{ZONE_ID}/export")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "SOA" in response.text
