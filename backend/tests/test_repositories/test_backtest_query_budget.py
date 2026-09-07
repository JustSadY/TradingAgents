from __future__ import annotations

from backend.repositories import backtest as backtest_repo


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


async def test_consensus_backtest_query_excludes_report_payloads() -> None:
    db = _CaptureDB()

    await backtest_repo.list_consensus_analyses(
        db,
        user_id=7,
        ticker="AAPL",
        start_date="2026-01-01",
        end_date="2026-09-01",
    )

    sql = str(db.statements[0].compile(compile_kwargs={"literal_binds": True})).lower()
    select_clause = sql.split(" from ", 1)[0]
    assert "analysis_results.signal" in select_clause
    assert "analysis_results.portfolio_decision_json" in select_clause
    assert "analysis_results.chart_annotations" in select_clause
    assert "analysis_results.market_report" not in select_clause
    assert "analysis_results.final_decision" not in select_clause
    assert "analysis_results.risk_debate_history" not in select_clause
