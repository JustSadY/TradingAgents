from __future__ import annotations

from backend.repositories import analysis_stats


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


async def test_completed_stats_query_excludes_report_payloads() -> None:
    db = _CaptureDB()

    await analysis_stats.list_completed_analyses_for_stats(db, user_id=7)

    select_clause = _select_clause(db.statements[0])
    assert "analysis_results.tokens_in" in select_clause
    assert "analysis_results.raw_return" in select_clause
    assert "analysis_results.preset_name" in select_clause
    assert "analysis_results.market_report" not in select_clause
    assert "analysis_results.final_decision" not in select_clause
    assert "analysis_results.strategy_after_json" not in select_clause


async def test_calibration_query_selects_only_decision_outcome_surface() -> None:
    db = _CaptureDB()

    await analysis_stats.list_learning_eligible_analyses(db, user_id=7, asset_type="stock")

    select_clause = _select_clause(db.statements[0])
    assert "analysis_results.portfolio_decision_json" in select_clause
    assert "analysis_results.signal" in select_clause
    assert "analysis_results.alpha_return" in select_clause
    assert "analysis_results.market_report" not in select_clause
    assert "analysis_results.final_decision" not in select_clause
    assert "analysis_results.risk_debate_history" not in select_clause


async def test_ticker_prefilter_query_excludes_strategy_and_debate_payloads() -> None:
    db = _CaptureDB()

    await analysis_stats.list_learning_eligible_ticker_analyses(db, user_id=7, ticker="AAPL")

    select_clause = _select_clause(db.statements[0])
    assert "analysis_results.raw_return" in select_clause
    assert "analysis_results.strategy_after_json" not in select_clause
    assert "analysis_results.final_decision" not in select_clause
    assert "analysis_results.risk_debate_history" not in select_clause
