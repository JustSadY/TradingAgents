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

class ToolAccessPerms(BaseModel):
    """What a user may do with one tool."""

    can_view: bool
    can_use: bool
    can_edit: bool
    can_enable: bool

class ToolFieldAccessPerms(BaseModel):
    """What a user may do with one setting field of one tool."""

    can_view: bool
    can_edit: bool

class ToolAccessPermsUpdate(BaseModel):
    """A partial permission change; omitted keys keep their stored value.

    ``extra="forbid"`` keeps the guarantee the service used to enforce by hand,
    that an unrecognised permission name is rejected rather than ignored.
    """

    model_config = ConfigDict(extra="forbid")

    can_view: bool | None = None
    can_use: bool | None = None
    can_edit: bool | None = None
    can_enable: bool | None = None

class ToolFieldAccessPermsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    can_view: bool | None = None
    can_edit: bool | None = None

# Access maps are keyed by agent key, tool key, and tool key -> field key. The
# keys are dynamic, but the values are not, so these describe the payload as
# precisely as it can be described — the routes used to return a bare dict.
AgentAccessMap = dict[str, bool]
ToolAccessMap = dict[str, ToolAccessPerms]
ToolFieldAccessMap = dict[str, dict[str, ToolFieldAccessPerms]]

class AgentAccessUpdateResponse(BaseModel):
    detail: str
    agents: AgentAccessMap

class ToolAccessUpdateResponse(BaseModel):
    detail: str
    tools: ToolAccessMap

class ToolFieldAccessUpdateResponse(BaseModel):
    detail: str
    fields: ToolFieldAccessMap
