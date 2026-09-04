from __future__ import annotations

from types import SimpleNamespace

from backend.repositories import analysis as analysis_repo


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


def _sql(statement) -> str:
    return str(statement.compile(compile_kwargs={"literal_binds": True})).lower()


async def test_analysis_history_selects_only_list_surface() -> None:
    db = _CaptureDB()
    user = SimpleNamespace(id=7, is_admin=False)

    await analysis_repo.list_analyses(db, user=user, limit=20, offset=0)

    sql = _sql(db.statements[0])
    select_clause = sql.split(" from ", 1)[0]
    assert "analysis_results.chart_annotations" in select_clause
    assert "analysis_results.raw_return" in select_clause
    assert "analysis_results.market_report" not in select_clause
    assert "analysis_results.final_decision" not in select_clause
    assert "analysis_results.strategy_after_json" not in select_clause
    assert "analysis_results.risk_debate_history" not in select_clause


async def test_portfolio_history_excludes_detail_only_payloads() -> None:
    db = _CaptureDB()
    user = SimpleNamespace(id=7, is_admin=False)

    await analysis_repo.list_multi_ticker_analyses(db, user=user, limit=20, offset=0)

    sql = _sql(db.statements[0])
    select_clause = sql.split(" from ", 1)[0]
    assert "multi_ticker_analyses.tickers" in select_clause
    assert "multi_ticker_analyses.super_portfolio_report" not in select_clause
    assert "multi_ticker_analyses.analysis_ids" not in select_clause
