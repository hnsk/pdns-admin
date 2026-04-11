# Plan: Multi-server zone list — one row per (zone, server)

## Context
Zone list currently deduplicates by zone name (first server wins). User wants: if same zone exists on multiple PowerDNS servers, show separate rows — one per server — each independently manageable (Manage / Delete scoped to that server). Typical use case: primary + secondary server holding the same zone.

---

## Implementation

### 1. Migration — `migrations/005_multiserver_zones.sql` (NEW)

Change `zone_server_map` from single-column PK `(zone_name)` to composite PK `(zone_name, pdns_server_id)`:

```sql
CREATE TABLE zone_server_map_new (
    zone_name      TEXT    NOT NULL,
    pdns_server_id INTEGER NOT NULL REFERENCES pdns_servers(id) ON DELETE RESTRICT,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (zone_name, pdns_server_id)
);
INSERT INTO zone_server_map_new SELECT zone_name, pdns_server_id, created_at FROM zone_server_map;
DROP TABLE zone_server_map;
ALTER TABLE zone_server_map_new RENAME TO zone_server_map;
CREATE INDEX idx_zone_server_map_server ON zone_server_map(pdns_server_id);
```

---

### 2. Repo — `app/repositories/pdns_server_repo.py`

**a. Add `get_server_for_zone_by_server_id(db, zone_name, pdns_server_db_id)`** — returns single server or None; used by dependency when `server_id` query param is present.

**b. Update `map_zone_to_server`** — change conflict clause:
```python
"INSERT INTO zone_server_map (zone_name, pdns_server_id) VALUES (?, ?) "
"ON CONFLICT(zone_name, pdns_server_id) DO NOTHING"
```

**c. Add `unmap_zone_from_server(db, zone_name, pdns_server_id)`** — deletes one specific `(zone, server)` row.

**d. Add `count_zone_servers(db, zone_name) -> int`** — counts remaining server mappings; used post-delete to decide if zone_assignments should be cleaned up.

Keep `unmap_zone` (deletes all rows for a zone) and `get_server_for_zone_or_fallback` unchanged — still used as fallback.

---

### 3. Dependency — `app/dependencies.py`

Add optional `server_id: int | None = Query(default=None)`:

```python
async def get_pdns_for_zone(
    zone_id: str,
    server_id: int | None = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
) -> PDNSClient:
    if server_id is not None:
        srv = await pdns_server_repo.get_server_for_zone_by_server_id(db, zone_id, server_id)
        if srv is None:
            raise HTTPException(404, "Zone not mapped to the specified server")
    else:
        srv = await pdns_server_repo.get_server_for_zone_or_fallback(db, zone_id)
        if srv is None:
            raise HTTPException(404, "Zone not mapped to any server")
    ...
```

All API routes using `Depends(get_pdns_for_zone)` gain `?server_id=N` support automatically.

---

### 4. API zones — `app/routers/api_zones.py`

Only `delete_zone` needs changes — scoped delete logic:

```python
@router.delete("/{zone_id}")
async def delete_zone(
    zone_id: str,
    server_id: int | None = Query(default=None),
    ...
):
    await pdns_client.delete_zone(zone_id)  # deletes from server resolved by dependency

    if server_id is not None:
        await pdns_server_repo.unmap_zone_from_server(db, zone_id, server_id)
        remaining = await pdns_server_repo.count_zone_servers(db, zone_id)
        if remaining == 0:
            await zone_assignment_repo.delete_zone_assignments(db, zone_id)
    else:
        # Legacy path
        await zone_assignment_repo.delete_zone_assignments(db, zone_id)
        await pdns_server_repo.unmap_zone(db, zone_id)

    await audit_repo.log_action(..., detail={"server_id": server_id})
```

---

### 5. Zone views — `app/views/zone_views.py`

**`zones_list`** — remove dedup, collect all (zone, server) pairs:

```python
# Remove: seen: dict[str, dict] = {}  and  if name not in seen
# Remove: zone_server_map correction block (lines 56-62)

all_zones = []
mapping_rows = await db.execute_fetchall("SELECT zone_name, pdns_server_id FROM zone_server_map")
mapped_pairs = {(row[0], row[1]) for row in mapping_rows}

for srv in active_servers:
    try:
        zones = await registry.get(srv["id"]).list_zones()
        for z in zones:
            name = z.get("name") or z.get("id")
            z["_server_id"] = srv["id"]
            z["_server_name"] = srv["name"]
            if (name, srv["id"]) not in mapped_pairs:
                await pdns_server_repo.map_zone_to_server(db, name, srv["id"])
                mapped_pairs.add((name, srv["id"]))
            all_zones.append(z)
    except (PDNSError, RuntimeError):
        pass
```

**`zone_detail`, `zone_export_page`, `zone_dnssec_page`** — add `server_id: int | None = Query(default=None)`, use `get_server_for_zone_by_server_id` when provided, else fall back. Pass `server_id` into template context.

---

### 6. Template — `app/templates/zones/list.html`

**Composite key** (line 50):
```html
<template x-for="zone in filtered" :key="zone.id + '::' + zone._server_id">
```

**Manage/name links** (lines 52, 62):
```html
<a :href="'/zones/' + zone.id + '?server_id=' + zone._server_id" ...>
```

**Delete function** (line 318):
```javascript
deleteZone(zone) {
    if (!confirm('Delete zone ' + zone.name + ' from ' + zone._server_name + '?')) return;
    fetch('/api/zones/' + zone.id + '?server_id=' + zone._server_id, { method: 'DELETE' })
        .then(r => r.ok ? location.reload() : r.json().then(d => alert(d.detail || 'Delete failed')));
}
```

---

### 7. Template — `app/templates/zones/detail.html`

Thread `server_id` through HTMX URLs (Jinja context var, integer or None):

```html
<button hx-put="/api/zones/{{ zone.id }}/notify{% if server_id %}?server_id={{ server_id }}{% endif %}">Notify</button>
<button hx-put="/api/zones/{{ zone.id }}/rectify{% if server_id %}?server_id={{ server_id }}{% endif %}">Rectify</button>
<a href="/zones/{{ zone.id }}/export{% if server_id %}?server_id={{ server_id }}{% endif %}">Export</a>
<a href="/zones/{{ zone.id }}/dnssec{% if server_id %}?server_id={{ server_id }}{% endif %}">DNSSEC Keys</a>
```

Also thread `server_id` through JS fetch calls inside the template (patch rrsets, etc.).

---

### 8. Template — `app/templates/zones/export.html`

Back link (line 6):
```html
<a href="/zones/{{ zone_id }}{% if server_id %}?server_id={{ server_id }}{% endif %}">← Back to Zone</a>
```

Pass `server_id` from `zone_export_page` view into template context.

---

## Critical files

| File | Change |
|------|--------|
| `migrations/005_multiserver_zones.sql` | NEW — composite PK |
| `app/repositories/pdns_server_repo.py` | +3 functions, update map_zone_to_server |
| `app/dependencies.py` | Optional server_id query param |
| `app/routers/api_zones.py` | delete_zone scoped logic |
| `app/views/zone_views.py` | Remove dedup, add server_id to detail routes |
| `app/templates/zones/list.html` | Composite key, server-scoped URLs |
| `app/templates/zones/detail.html` | Thread server_id through HTMX URLs |
| `app/templates/zones/export.html` | server_id on back link |

## Verification

1. Start app — migration 005 applies on startup
2. Zone list shows one row per (zone, server) — same zone on 2 servers = 2 rows
3. Manage link for each row opens correct server's zone detail
4. Delete from one row deletes only from that server; other row remains
5. Zone assignments only deleted when last server mapping removed
6. Export/DNSSEC pages route to correct server
7. Single-server setup: behavior unchanged (one row per zone)