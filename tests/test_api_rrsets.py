import pytest
from unittest.mock import AsyncMock

from app.pdns_client import PDNSError


ZONE_ID = "example.com."
RRSETS_URL = f"/api/zones/{ZONE_ID}/rrsets"

A_RECORD_PAYLOAD = [
    {
        "name": "test.example.com.",
        "type": "A",
        "ttl": 300,
        "records": [{"content": "1.2.3.4", "disabled": False}],
    }
]

TXT_RECORD_PAYLOAD = [
    {
        "name": "example.com.",
        "type": "TXT",
        "ttl": 300,
        "records": [{"content": "v=spf1 include:example.com ~all", "disabled": False}],
    }
]


# --- Basic REPLACE ---

async def test_patch_rrsets_happy_path(client_as_admin):
    ac, mock_pdns = client_as_admin
    response = await ac.patch(RRSETS_URL, json=A_RECORD_PAYLOAD)
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    mock_pdns.patch_rrsets.assert_called_once()
    call_args = mock_pdns.patch_rrsets.call_args
    assert call_args[0][0] == ZONE_ID


# --- TXT quoting ---

async def test_txt_content_gets_quoted(client_as_admin):
    ac, mock_pdns = client_as_admin
    response = await ac.patch(RRSETS_URL, json=TXT_RECORD_PAYLOAD)
    assert response.status_code == 200
    call_args = mock_pdns.patch_rrsets.call_args
    payload = call_args[0][1]
    assert payload[0]["records"][0]["content"] == '"v=spf1 include:example.com ~all"'


async def test_already_quoted_txt_not_double_quoted(client_as_admin):
    ac, mock_pdns = client_as_admin
    payload = [
        {
            "name": "example.com.",
            "type": "TXT",
            "ttl": 300,
            "records": [{"content": '"already quoted"', "disabled": False}],
        }
    ]
    await ac.patch(RRSETS_URL, json=payload)
    call_args = mock_pdns.patch_rrsets.call_args
    sent = call_args[0][1][0]["records"][0]["content"]
    assert sent == '"already quoted"'


async def test_spf_type_gets_quoted(client_as_admin):
    ac, mock_pdns = client_as_admin
    payload = [
        {
            "name": "example.com.",
            "type": "SPF",
            "ttl": 300,
            "records": [{"content": "v=spf1 ~all", "disabled": False}],
        }
    ]
    await ac.patch(RRSETS_URL, json=payload)
    call_args = mock_pdns.patch_rrsets.call_args
    sent = call_args[0][1][0]["records"][0]["content"]
    assert sent == '"v=spf1 ~all"'


async def test_a_record_content_unchanged(client_as_admin):
    ac, mock_pdns = client_as_admin
    await ac.patch(RRSETS_URL, json=A_RECORD_PAYLOAD)
    call_args = mock_pdns.patch_rrsets.call_args
    sent = call_args[0][1][0]["records"][0]["content"]
    assert sent == "1.2.3.4"


async def test_mx_record_content_unchanged(client_as_admin):
    ac, mock_pdns = client_as_admin
    payload = [
        {
            "name": "example.com.",
            "type": "MX",
            "ttl": 300,
            "records": [{"content": "10 mail.example.com.", "disabled": False}],
        }
    ]
    await ac.patch(RRSETS_URL, json=payload)
    call_args = mock_pdns.patch_rrsets.call_args
    sent = call_args[0][1][0]["records"][0]["content"]
    assert sent == "10 mail.example.com."


# --- DELETE changetype ---

async def test_delete_changetype_passed_through(client_as_admin):
    ac, mock_pdns = client_as_admin
    payload = [
        {
            "name": "test.example.com.",
            "type": "A",
            "ttl": 300,
            "records": [],
            "changetype": "DELETE",
        }
    ]
    response = await ac.patch(RRSETS_URL, json=payload)
    assert response.status_code == 200
    call_args = mock_pdns.patch_rrsets.call_args
    sent = call_args[0][1]
    assert sent[0]["changetype"] == "DELETE"


# --- Bulk ---

async def test_bulk_two_rrsets(client_as_admin):
    ac, mock_pdns = client_as_admin
    payload = [
        {
            "name": "a.example.com.",
            "type": "A",
            "ttl": 300,
            "records": [{"content": "1.2.3.4", "disabled": False}],
        },
        {
            "name": "example.com.",
            "type": "MX",
            "ttl": 300,
            "records": [{"content": "10 mail.example.com.", "disabled": False}],
        },
    ]
    response = await ac.patch(RRSETS_URL, json=payload)
    assert response.status_code == 200
    call_args = mock_pdns.patch_rrsets.call_args
    assert len(call_args[0][1]) == 2


async def test_bulk_two_rrsets_audit_entries(db, client_as_admin):
    ac, mock_pdns = client_as_admin
    payload = [
        {
            "name": "a.example.com.",
            "type": "A",
            "ttl": 300,
            "records": [{"content": "1.2.3.4", "disabled": False}],
        },
        {
            "name": "example.com.",
            "type": "MX",
            "ttl": 300,
            "records": [{"content": "10 mail.example.com.", "disabled": False}],
        },
    ]
    await ac.patch(RRSETS_URL, json=payload)
    rows = await db.execute_fetchall("SELECT action FROM audit_log")
    assert len(rows) == 2


# --- Error propagation ---

async def test_pdns_error_propagated(client_as_admin):
    ac, mock_pdns = client_as_admin
    mock_pdns.patch_rrsets.side_effect = PDNSError(422, "Invalid record")
    response = await ac.patch(RRSETS_URL, json=A_RECORD_PAYLOAD)
    assert response.status_code == 422


async def test_invalid_body_missing_name(client_as_admin):
    ac, mock_pdns = client_as_admin
    bad_payload = [{"type": "A", "ttl": 300, "records": [{"content": "1.2.3.4"}]}]
    response = await ac.patch(RRSETS_URL, json=bad_payload)
    assert response.status_code == 422


async def test_empty_rrsets_list(client_as_admin):
    ac, mock_pdns = client_as_admin
    response = await ac.patch(RRSETS_URL, json=[])
    assert response.status_code == 200
    mock_pdns.patch_rrsets.assert_called_once_with(ZONE_ID, [])


# --- Audit action names ---

async def test_audit_action_replace(db, client_as_admin):
    ac, mock_pdns = client_as_admin
    await ac.patch(RRSETS_URL, json=A_RECORD_PAYLOAD)
    rows = await db.execute_fetchall("SELECT action FROM audit_log WHERE action = 'record.replace'")
    assert len(rows) == 1


async def test_audit_action_delete(db, client_as_admin):
    ac, mock_pdns = client_as_admin
    payload = [
        {
            "name": "test.example.com.",
            "type": "A",
            "ttl": 300,
            "records": [],
            "changetype": "DELETE",
        }
    ]
    await ac.patch(RRSETS_URL, json=payload)
    rows = await db.execute_fetchall("SELECT action FROM audit_log WHERE action = 'record.delete'")
    assert len(rows) == 1
