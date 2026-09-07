"""Which tables Alembic autogenerate is allowed to have an opinion about.

A few tables exist in the database with no ORM model behind them. Without this,
autogenerate compares them against `Base.metadata`, finds nothing, and offers to
drop them — which is both wrong and noisy enough to hide a real difference.

Lives here rather than in `alembic/env.py` so the drift test can apply the same
policy the migrations do, instead of a copy of it.
"""

from typing import Any

#: LangGraph creates and owns its checkpoint tables through an idempotent
#: ``setup()`` that runs once per process, which is why they are deliberately
#: not under Alembic.
NON_ORM_TABLES = frozenset(
    {
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
        "checkpoint_migrations",
    }
)


def include_object(obj: Any, name: str, type_: str, reflected: bool, compare_to: Any) -> bool:
    """`include_object` hook for Alembic autogenerate."""
    if type_ == "table" and name in NON_ORM_TABLES:
        return False
    return True
