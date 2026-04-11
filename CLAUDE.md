# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install deps (dev extras include pytest + ruff)
pip install -e ".[dev]"

# Run the app locally
uvicorn app.main:app --reload --port 8080

# Lint
ruff check app/

# Format
ruff format app/

# Run all tests
pytest

# Run a single test file
pytest tests/test_foo.py

# Docker
docker compose up --build
```

## Architecture

**Stack:** FastAPI + aiosqlite (SQLite) + Jinja2/HTMX/Alpine.js. No ORM — raw SQL via `aiosqlite`. Single global DB connection initialized at startup and injected via FastAPI's `Depends(get_db)`.

**Startup sequence** (`app/main.py` lifespan):
1. `init_db()` — connect to SQLite, run any unapplied migrations from `migrations/*.sql` (alphabetical order)
2. `seed_defaults()` — write env var values into `settings` table only if those keys are absent
3. Load `settings` table → `pdns.start(url, key, server_id)` — builds the `httpx.AsyncClient`
4. `ensure_admin_exists()` — creates the admin user on first boot

**PowerDNS client** (`app/pdns_client.py`): Singleton `pdns`. All calls to PowerDNS go through this. Call `pdns.reconfigure(url, key, server_id)` to swap the live connection without restarting (used by the settings save endpoint).

**Two-layer routing:** API routes (`/api/…`) return JSON; view routes (`/`, `/zones`, `/settings`, etc.) return HTML via Jinja2 templates. Both layers live under `app/routers/` and `app/views/` respectively, and are registered in `main.py`.

**Auth:** Session cookie (`session_id`) or `X-API-Key` header. `get_current_user` → `require_admin` dependency chain used in both API and view routers. Operators can only see zones explicitly assigned to them (`zone_assignments` table).

**Database access pattern:** Repositories (`app/repositories/`) contain all SQL. Routers call repository functions — never write SQL directly in routers or views.

**Settings persistence:** PowerDNS connection settings (`pdns_api_url`, `pdns_api_key`, `pdns_server_id`) live in the `settings` table. Env vars (`POWERADMIN_PDNS_API_*`) only seed initial values; the UI (`/settings`) is authoritative after first boot.

**Migrations:** Drop a new numbered `.sql` file in `migrations/` (e.g. `003_foo.sql`). It runs automatically on next startup and is tracked in `_migrations`.

**Audit log:** Call `audit_repo.log_action(db, user_id, username, "resource.verb", zone_name, detail_dict)` in any mutating endpoint. Action string convention: `noun.verb` (e.g. `zone.create`, `settings.pdns.update`).

**Frontend:** Templates extend `base.html`. HTMX handles dynamic updates (no full-page reloads for record edits, etc.). Alpine.js manages component-local state. CSS variables for theming are defined in `base.html`'s `<style>` block — no external CSS framework.
