# Plan: DNS Tools Page

## Context

The app currently has no dedicated tools/diagnostics page. Users need a way to perform ad-hoc DNS operations — zone exports (AXFR), record lookups, and zone search — directly from the UI. A key requirement is the ability to compare results across multiple configured PowerDNS servers (e.g. checking if a zone is in sync) and to get plain-text output for scripting/copy-paste.

## Overview

Add a `/tools` page with three tools:
1. **Zone Export** — export a full zone file (via PowerDNS export API) from one or more servers
2. **Record Lookup** — query specific rrsets from a zone across one or more servers
3. **Zone Search** — use PowerDNS search API across selected servers

All tools support:
- **Multi-server selection** — run on one, several, or all active servers and display results per-server
- **Comparison view** — when multiple servers are selected, highlight differences between results
- **Plain-text output** — a raw/plain text button that opens a `/api/tools/*/text` endpoint returning `text/plain` for copy/download

Access: all authenticated users (admin and operator).

---

## Files to Create

### `app/routers/api_tools.py`
API router mounted at `/api/tools`. Three endpoints:

```
POST /api/tools/axfr
  Body: { zone_id: str, server_ids: list[int] }
  Returns: { results: [{ server_id, server_name, text, error }] }

POST /api/tools/lookup
  Body: { zone_id: str, name: str, rtype: str, server_ids: list[int] }
  Returns: { results: [{ server_id, server_name, rrsets: [...], error }] }

POST /api/tools/search
  Body: { query: str, object_type: str, max_results: int, server_ids: list[int] }
  Returns: { results: [{ server_id, server_name, hits: [...], error }] }
```

Plain-text format: each endpoint accepts `Accept: text/plain` header → returns `text/plain` with labeled sections per server, suitable for download.

Implementation uses `registry.get(server_id)` for each requested server, runs calls concurrently with `asyncio.gather`, collects errors per server without raising globally.

Authorization: uses `get_current_user` dependency (session or API key). Operators can only query zones they have access to (check `zone_assignment_repo`).

### `app/views/tools_views.py`
View router, one route:
```
GET /tools  →  renders tools.html
```
Passes `active_servers` (list of active pdns_servers rows) and `record_types` list to the template.

### `app/templates/tools.html`
Extends `base.html`. Single Alpine.js component (`x-data="toolsPage()"`) with tab navigation for the three tools.

**Tabs:** Zone Export | Record Lookup | Zone Search

**Shared UI patterns:**
- Server multi-select checkboxes (pre-populated from `active_servers`)
- "Select All / None" toggle
- Submit button → calls the relevant `/api/tools/*` endpoint via `fetch`
- Results area: one card per server, labeled with server name
- If multiple servers selected: "Compare" button appears → diffs the outputs side by side (text comparison using split-pane layout)
- Plain Text button → calls same endpoint with `Accept: text/plain`, triggers `Blob` download

**Zone Export tab:**
- Zone name text input
- Server selection
- Output: `<pre class="mono">` block per server with zone file text

**Record Lookup tab:**
- Zone name input
- Record name input (supports `@` for apex)
- Record type dropdown (full RECORD_TYPES list)
- Server selection
- Output: table of rrsets per server, or "No records found"

**Zone Search tab:**
- Search query input
- Object type select: All / Zones / Records
- Max results input (default 100)
- Server selection
- Output: table with columns: Type, Name, Zone, Content, Server

**Comparison logic (client-side Alpine.js):**
When multiple servers return results, the component compares them:
- For zone export: text diff line-by-line (lines only in server A highlighted red, only in server B highlighted green, common lines gray)
- For record lookup: set comparison on rrset content strings — mark mismatches

---

## Files to Modify

### `app/main.py`
Add router imports and `app.include_router` calls:
```python
from app.routers import api_tools
from app.views import tools_views
app.include_router(api_tools.router)
app.include_router(tools_views.router)
```

### `app/templates/base.html`
Add "Tools" nav link after the Zones link (visible to all authenticated users):
```html
<a href="/tools" class="{% if active_page == 'tools' %}active{% endif %}">Tools</a>
```

---

## Reuse Existing Code

| Need | Existing function |
|---|---|
| PowerDNS API calls | `registry.get(server_db_id)` → `PDNSClient` methods: `export_zone()`, `get_zone()`, `search()` |
| List active servers | `pdns_server_repo.list_servers(db)` + filter `is_active` |
| User auth | `get_current_user` dependency from `app/auth.py` |
| Zone access check (operators) | `zone_assignment_repo.get_user_zone_assignments(db, user.id)` |
| Record type list | `RECORD_TYPES` constant from `zone_views.py` (import or duplicate) |
| CSS/layout | Existing `.card`, `.btn`, `.mono`, `.tabs`, `.tab`, `.badge-*`, `.flash-*` classes |

---

## Verification

1. Start the app: `uvicorn app.main:app --reload`
2. Log in as admin → verify "Tools" appears in navbar
3. Log in as operator → verify "Tools" also appears
4. **Zone Export**: enter a known zone name, select one server → verify zone file appears in `<pre>` block
5. **Zone Export plain text**: click Plain Text → browser downloads raw zone file
6. **Record Lookup**: query an A record → verify record content shown
7. **Multi-server compare**: select 2 servers for zone export → verify per-server sections render; click Compare → diff view shows
8. **Zone Search**: search for a hostname fragment → results appear with correct server labels
9. **Error handling**: select a server that's down → verify that server shows error message without breaking other results
10. **Operator access**: log in as operator with restricted zones → verify they can only query their assigned zones
