# PowerAdmin

> **Notice:** This is a personal learning exercise. No maintenance planned. Not suitable for production use.

Lightweight web-based management interface for PowerDNS Authoritative Server.

## Features

- **Zone Management** - Create, edit, delete DNS zones with full record management
- **All RR Types** - Supports every record type PowerDNS supports (A, AAAA, CNAME, MX, SRV, TXT, CAA, TLSA, SVCB, HTTPS, and 40+ more)
- **DNSSEC** - Enable/disable DNSSEC signing, manage cryptokeys, retrieve DS records for delegation
- **User Management** - Admin and operator roles with per-zone access control
- **Audit Log** - Full audit trail of all zone and user management actions
- **API** - REST API with session and API key authentication
- **PowerDNS API** - Communicates with PowerDNS via its native HTTP API

## Quick Start

```bash
# Clone and configure
cp .env.example .env
# Edit .env to set secure passwords and keys

# Start with Docker Compose
docker compose up -d

# Access at http://localhost:8080
# Default login: admin / admin
```

## Configuration

All configuration is via environment variables (prefixed with `POWERADMIN_`):

| Variable | Default | Description |
|---|---|---|
| `POWERADMIN_PDNS_API_URL` | `http://localhost:8081` | PowerDNS API URL |
| `POWERADMIN_PDNS_API_KEY` | `changeme` | PowerDNS API key |
| `POWERADMIN_PDNS_SERVER_ID` | `localhost` | PowerDNS server ID |
| `POWERADMIN_DATABASE_PATH` | `/data/poweradmin.db` | SQLite database path |
| `POWERADMIN_SECRET_KEY` | (insecure default) | Session signing secret |
| `POWERADMIN_SESSION_LIFETIME_HOURS` | `8` | Session expiry in hours |
| `POWERADMIN_DEFAULT_ADMIN_PASSWORD` | `admin` | Initial admin password (first run only) |

## Roles

| Capability | Admin | Operator |
|---|---|---|
| Create/delete zones | Yes | No |
| Manage records in assigned zones | All zones | Assigned only |
| DNSSEC key management | Yes | No |
| User management | Yes | No |
| View audit log | All entries | Own actions |
| Zone export/notify/rectify | All zones | Assigned only |

## API

Interactive API docs available at `/docs` (Swagger UI) and `/redoc` when the server is running.

### Authentication

- **Session**: Login via `POST /api/login` with `{"username": "...", "password": "..."}`, uses `session_id` cookie
- **API Key**: Create via `POST /api/api-keys`, then pass `X-API-Key: <key>` header

### Key Endpoints

```
POST   /api/login
GET    /api/zones
POST   /api/zones
GET    /api/zones/{id}
DELETE /api/zones/{id}
PATCH  /api/zones/{id}/rrsets        # Create/update/delete records
GET    /api/zones/{id}/export
GET    /api/zones/{id}/cryptokeys    # DNSSEC keys
POST   /api/zones/{id}/cryptokeys
POST   /api/zones/{id}/dnssec/enable
GET    /api/users
POST   /api/users
GET    /api/audit
```

## Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run locally (requires PowerDNS running)
export POWERADMIN_PDNS_API_URL=http://localhost:8081
export POWERADMIN_PDNS_API_KEY=your-key
export POWERADMIN_DATABASE_PATH=./poweradmin.db
uvicorn app.main:app --reload --port 8080
```

## Tech Stack

- **Backend**: Python, FastAPI, aiosqlite, httpx
- **Frontend**: Jinja2 templates, htmx, Alpine.js
- **Database**: SQLite (app data), PowerDNS API (DNS data)
- **Auth**: Server-side sessions with bcrypt password hashing
