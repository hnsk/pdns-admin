import pytest
from pydantic import ValidationError

from app.routers.api_zones import _ensure_quoted
from app.models.zone import Record, RRSet, ZoneCreate, ZoneUpdate


# --- _ensure_quoted ---

def test_ensure_quoted_already_quoted():
    assert _ensure_quoted('"hello"') == '"hello"'


def test_ensure_quoted_plain_text():
    assert _ensure_quoted("hello") == '"hello"'


def test_ensure_quoted_inner_quotes():
    # say "hi" → "say \"hi\""
    result = _ensure_quoted('say "hi"')
    assert result == '"say \\"hi\\""'


def test_ensure_quoted_backslashes():
    # a\b → "a\\b"
    result = _ensure_quoted("a\\b")
    assert result == '"a\\\\b"'


def test_ensure_quoted_whitespace_stripped():
    assert _ensure_quoted("  hello  ") == '"hello"'


def test_ensure_quoted_empty_quoted_string():
    # '""' is already quoted (starts+ends with " and len>=2)
    assert _ensure_quoted('""') == '""'


# --- Record model ---

def test_record_defaults():
    r = Record(content="1.2.3.4")
    assert r.content == "1.2.3.4"
    assert r.disabled is False


def test_record_no_args():
    with pytest.raises(ValidationError):
        Record()


# --- RRSet model ---

def test_rrset_defaults():
    rs = RRSet(name="example.com.", type="A", ttl=300, records=[Record(content="1.2.3.4")])
    assert rs.changetype == "REPLACE"
    assert rs.comments is None


def test_rrset_all_fields():
    rs = RRSet(
        name="example.com.",
        type="TXT",
        ttl=300,
        records=[Record(content='"v=spf1 include:example.com ~all"')],
        changetype="DELETE",
        comments=[{"content": "test comment"}],
    )
    assert rs.changetype == "DELETE"
    assert rs.comments is not None


# --- ZoneCreate model ---

def test_zone_create_missing_server_id():
    with pytest.raises(ValidationError):
        ZoneCreate(name="x.com.")


def test_zone_create_valid():
    z = ZoneCreate(name="x.com.", server_id=1)
    assert z.kind == "Native"
    assert z.nameservers == []
    assert z.masters == []


# --- ZoneUpdate model ---

def test_zone_update_empty():
    z = ZoneUpdate()
    assert z.model_dump(exclude_none=True) == {}


def test_zone_update_with_kind():
    z = ZoneUpdate(kind="Slave")
    assert z.model_dump(exclude_none=True) == {"kind": "Slave"}
