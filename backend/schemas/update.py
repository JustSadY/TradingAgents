from pydantic import BaseModel, Field


class UpdateLastRun(BaseModel):
    """State persisted by the updater unit between runs."""

    state: str | None = None
    at: str | None = None
    error: str | None = None


class UpdateStatus(BaseModel):
    git: bool
    update_supported: bool
    current: str | None = None
    current_short: str | None = None
    latest_short: str | None = None
    behind: int = 0
    update_available: bool = False
    updating: bool = False
    last_update: UpdateLastRun = Field(default_factory=UpdateLastRun)
    commits: list[str] = Field(default_factory=list)


class UpdateApplyResult(BaseModel):
    started: bool
