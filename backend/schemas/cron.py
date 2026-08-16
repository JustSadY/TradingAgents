"""Response contract for the scheduler status indicator."""

from pydantic import BaseModel


class CronStatusResponse(BaseModel):
    #: Whether the scheduler process itself is running.
    running: bool
    #: Whether this user has a watchlist scan job registered.
    job_configured: bool
    next_run_time: str | None = None
