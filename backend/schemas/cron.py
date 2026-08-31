"""Response contract for the scheduler status indicator.

The indicator used to publish a single latched boolean that was set when the
process started and never cleared, so a scheduler that had stopped, stalled or
lost its job registration still showed as online. The fields below carry enough
to tell those apart without reading the server logs.
"""

from pydantic import BaseModel


class CronStatusResponse(BaseModel):
    #: Whether APScheduler itself reports as running right now.
    running: bool
    #: Whether this user has a watchlist scan job registered.
    job_configured: bool
    next_run_time: str | None = None

    #: Why the scheduler cannot be trusted, as a stable code the UI translates:
    #: ``scheduler_not_initialized``, ``scheduler_stopped``, ``scheduler_stalled``,
    #: ``bootstrap_failed`` or ``job_missing``. ``None`` means healthy.
    degraded_reason: str | None = None
    #: Free-text elaboration on ``degraded_reason`` (an error message, an age).
    degraded_detail: str | None = None

    #: The cron expression currently registered, which is not necessarily the
    #: one stored in settings if registration failed.
    schedule: str | None = None
    #: IANA timezone the schedule is interpreted in (``APP_TIMEZONE``).
    timezone: str | None = None

    #: When the scheduler last started, and the liveness beat it refreshes on a
    #: timer. APScheduler reports ``running`` from ``start()`` onwards, so a
    #: stale heartbeat is the only way to see a wedged event loop.
    started_at: str | None = None
    last_heartbeat_at: str | None = None
    heartbeat_age_seconds: float | None = None
    #: When the stored cron settings were last replayed onto the scheduler.
    last_resync_at: str | None = None

    #: When this user's scan last actually queued analyses. Read back from the
    #: analyses it created, so it survives a restart.
    last_run_at: str | None = None
    #: Outcome of the last attempt in this process: ``ok``, ``skipped``,
    #: ``error``, ``missed`` or ``running``.
    last_outcome: str | None = None
    last_outcome_at: str | None = None
    #: Why the last attempt ended that way — an exchange holiday, an empty
    #: watchlist, a lock held elsewhere, an exception.
    last_outcome_detail: str | None = None
