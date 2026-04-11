from pydantic import BaseModel


class User(BaseModel):
    id: int
    username: str
    role: str  # "admin" or "operator"
    is_active: bool


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "operator"


class UserUpdate(BaseModel):
    password: str | None = None
    role: str | None = None
    is_active: bool | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str
