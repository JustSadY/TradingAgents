"""Persistent, exact-state asset strategy records.

``AssetStrategy`` is deliberately separate from episodic/vector memory.  It
holds the one current belief for an owner/instrument, while
``AssetStrategyVersion`` is an append-only audit ledger of the beliefs that
were accepted over time.  The repository is the only application write path
for version rows; it always creates a new row when the current strategy is
changed.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base

ASSET_STRATEGY_ACTIVE = "ACTIVE"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AssetStrategy(Base):
    """The current exact strategy state for one owner, ticker, and asset type.

    The partial unique expression index intentionally uses ``COALESCE`` so a
    system-owned strategy (``user_id IS NULL``) is unique too.  A conventional
    nullable composite unique constraint would allow multiple NULL-owned rows
    in PostgreSQL and would therefore not enforce the desired invariant.
    """

    __tablename__ = "asset_strategies"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_asset_strategies_version_positive"),
        CheckConstraint(
            "conviction >= 0.0 AND conviction <= 1.0",
            name="ck_asset_strategies_conviction_probability",
        ),
        Index("ix_asset_strategies_owner_ticker_asset_type", "user_id", "ticker", "asset_type"),
        Index("ix_asset_strategies_effective_recorded", "effective_at", "recorded_at"),
        # PostgreSQL's ordinary unique constraints consider NULL values
        # distinct.  SQLite supports this same expression + partial-index
        # syntax, so keeping it in metadata also preserves the invariant in
        # the lightweight local/test database path.
        Index(
            "uq_asset_strategies_active_owner_ticker_asset_type",
            text("COALESCE(user_id, -1)"),
            "ticker",
            "asset_type",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
            sqlite_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    ticker: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False, default="stock")

    # Lifecycle status of this current strategy row.  Only ACTIVE participates
    # in the owner/ticker uniqueness invariant; CLOSED/INVALIDATED rows remain
    # available for historical queries and audit.
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ASSET_STRATEGY_ACTIVE,
        server_default=ASSET_STRATEGY_ACTIVE,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    strategic_bias: Mapped[str] = mapped_column(
        String(30), nullable=False, default="NEUTRAL", server_default="NEUTRAL"
    )
    conviction: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0.0")
    accepted_rating: Mapped[str | None] = mapped_column(String(30), nullable=True)
    thesis: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    key_drivers: Mapped[list | dict] = mapped_column(JSON, nullable=False, default=list)
    watch_conditions: Mapped[list | dict] = mapped_column(JSON, nullable=False, default=list)
    invalidation_conditions: Mapped[list | dict] = mapped_column(JSON, nullable=False, default=list)
    open_questions: Mapped[list | dict] = mapped_column(JSON, nullable=False, default=list)
    regime_assumption: Mapped[dict | list] = mapped_column(JSON, nullable=False, default=dict)
    time_horizon: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # A strategy is allowed to outlive the analysis run that informed it.  The
    # FK consequently uses SET NULL rather than deleting strategy evidence.
    last_analysis_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("analysis_results.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Bitemporal fields: effective_at is the business/as-of time represented
    # by the belief; recorded_at is when this system learned/persisted it.
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    versions: Mapped[list[AssetStrategyVersion]] = relationship(
        "AssetStrategyVersion",
        back_populates="strategy",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AssetStrategyVersion.version",
    )


class AssetStrategyVersion(Base):
    """Immutable accepted-state ledger entry for an :class:`AssetStrategy`.

    Rows are intentionally never updated by the repository.  ``analysis_id``
    is nullable because deleting an analysis result must preserve the strategy
    audit trail while removing the now-dangling provenance reference.
    """

    __tablename__ = "asset_strategy_versions"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_asset_strategy_versions_version_positive"),
        UniqueConstraint("strategy_id", "version", name="uq_asset_strategy_versions_strategy_version"),
        Index("ix_asset_strategy_versions_strategy_effective_recorded", "strategy_id", "effective_at", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("asset_strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    analysis_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("analysis_results.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    revision_action: Mapped[str] = mapped_column(String(30), nullable=False)

    # Snapshot fields make the historical answer independent of later updates
    # to the mutable current row.  ``before_state`` is None for CREATE.
    before_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_state: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    triggered_invalidations: Mapped[list | dict] = mapped_column(JSON, nullable=False, default=list)
    supporting_evidence: Mapped[list | dict] = mapped_column(JSON, nullable=False, default=list)
    regime_before: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    regime_after: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    pm_proposed_rating: Mapped[str | None] = mapped_column(String(30), nullable=True)
    accepted_rating: Mapped[str | None] = mapped_column(String(30), nullable=True)
    change_strength: Mapped[float | None] = mapped_column(Float, nullable=True)

    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    strategy: Mapped[AssetStrategy] = relationship("AssetStrategy", back_populates="versions")


@event.listens_for(AssetStrategyVersion, "before_update")
def _prevent_asset_strategy_version_mutation(mapper, connection, target) -> None:
    """Keep normal ORM writes from silently rewriting the audit ledger.

    The database may still null ``analysis_id`` through its ``ON DELETE SET
    NULL`` foreign-key action, which bypasses ORM events and deliberately
    preserves the version row.  Application changes must instead append a new
    version through ``repositories.asset_strategy``.
    """

    raise ValueError("AssetStrategyVersion rows are immutable; append a new version instead")
