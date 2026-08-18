from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=512)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SetupStatusResponse(BaseModel):
    """Whether the installation still needs its first (owner) account."""

    setup_required: bool


class SetupRequest(BaseModel):
    """First-run owner registration; accepted only while no user exists."""

    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=128)
    email: str | None = Field(default=None, max_length=255)
    display_name: str | None = Field(default=None, max_length=100)
