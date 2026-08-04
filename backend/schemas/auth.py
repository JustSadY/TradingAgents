from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=512)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    # Deprecated compatibility field. Browser responses intentionally omit it;
    # refresh credentials are delivered only in an HttpOnly cookie.
    refresh_token: str | None = None


class RefreshRequest(BaseModel):
    # Optional for cookie-authenticated browser clients. Kept for CLI/API
    # clients that cannot use the HttpOnly browser cookie.
    refresh_token: str | None = Field(default=None, min_length=1, max_length=4096)
