from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class UserCreate(BaseModel):
    username: str
    password: str = Field(min_length=8, max_length=128)
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

    model_config = ConfigDict(from_attributes=True)

class ProfileUpdate(BaseModel):
    email: str | None = None
    display_name: str | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)

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
    provider: str
    api_key: str

    @model_validator(mode="after")
    def reject_server_managed_provider_credentials(self) -> "ApiKeySet":
        """Ollama is configured by the server operator, never by a tenant.

        Older versions overloaded this field as a custom Ollama base URL.  It
        is a no-key provider whose endpoint is server-managed, so retaining a
        tenant value of *any* shape only creates inert, misleading state (and
        a URL would additionally be an SSRF risk).
        """
        if self.provider.strip().lower() == "ollama":
            raise ValueError("Ollama is configured by the server administrator, not via a tenant API key")
        return self

class PagePermissionsUpdate(BaseModel):
    permissions: dict[str, bool]

class PagePermissionsRead(BaseModel):
    allowed_pages: list[str]

class ApiKeyProvidersResponse(BaseModel):
    providers: list[str]

class SettingPermissionsResponse(BaseModel):
    allowed_settings: list[str]

class UserPermissionsResponse(BaseModel):
    user_id: int
    permissions: dict[str, bool]

class AgentAccessUpdateResponse(BaseModel):
    detail: str
    agents: dict

class ToolAccessUpdateResponse(BaseModel):
    detail: str
    tools: dict

class ToolFieldAccessUpdateResponse(BaseModel):
    detail: str
    fields: dict
