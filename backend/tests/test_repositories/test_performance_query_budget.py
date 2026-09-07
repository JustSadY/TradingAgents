from __future__ import annotations

from backend.repositories import performance as performance_repo


class _Scalars:
    def all(self):
        return []


class _Result:
    def scalars(self):
        return _Scalars()


class _CaptureDB:
    def __init__(self) -> None:
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result()


def _select_clause(statement) -> str:
    sql = str(statement.compile(compile_kwargs={"literal_binds": True})).lower()
    return sql.split(" from ", 1)[0]


async def test_resolved_learning_query_excludes_operational_payloads() -> None:
    db = _CaptureDB()

    await performance_repo.list_resolved_learning_analyses(db, user_id=7)

    select_clause = _select_clause(db.statements[0])
    assert "analysis_results.raw_return" in select_clause
    assert "analysis_results.alpha_return" in select_clause
    assert "analysis_results.market_regime_json" in select_clause
    assert "analysis_results.strategy_after_json" not in select_clause
    assert "analysis_results.risk_debate_history" not in select_clause
    assert "analysis_results.final_decision" not in select_clause


async def test_return_backfill_query_loads_only_backfill_surface() -> None:
    db = _CaptureDB()

    await performance_repo.list_return_backfill_candidates(
        db,
        cutoff_trade_date="2026-08-01",
        limit=50,
    )

    select_clause = _select_clause(db.statements[0])
    assert "analysis_results.final_decision" in select_clause
    assert "analysis_results.market_report" in select_clause
    assert "analysis_results.reflection" in select_clause
    assert "analysis_results.strategy_after_json" not in select_clause
    assert "analysis_results.risk_debate_history" not in select_clause
    assert "analysis_results.synthesis_report" not in select_clause
