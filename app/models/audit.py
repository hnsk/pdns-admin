from pydantic import BaseModel


class AuditEntry(BaseModel):
    id: int
    user_id: int | None
    username: str | None
    action: str
    zone_name: str | None
    detail: str | None
    created_at: str
