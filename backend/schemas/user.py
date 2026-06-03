from datetime import datetime
from pydantic import BaseModel, EmailStr, field_validator


class UserCreate(BaseModel):
    username: str
    password: str
    email: str | None = None
    display_name: str | None = None
    role: str = "user"

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("admin", "user", "owner"):
            raise ValueError("role must be 'admin', 'user' or 'owner'")
        return v


class UserRead(BaseModel):
    id: int
    username: str
    email: str | None = None
    display_name: str | None = None
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ProfileUpdate(BaseModel):
    email: str | None = None
    display_name: str | None = None
    password: str | None = None  # new plaintext password — hashed server-side


class UserAdminUpdate(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    email: str | None = None
    display_name: str | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str | None) -> str | None:
        if v is not None and v not in ("admin", "user", "owner"):
            raise ValueError("role must be 'admin', 'user' or 'owner'")
        return v


class ApiKeySet(BaseModel):
    """Set one provider's API key."""
    provider: str
    api_key: str


class PagePermissionsUpdate(BaseModel):
    """Map of page_key → allowed (True/False)."""
    permissions: dict[str, bool]


class PagePermissionsRead(BaseModel):
    """Allowed page keys for the requesting user."""
    allowed_pages: list[str]
