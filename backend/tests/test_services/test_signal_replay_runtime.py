from __future__ import annotations

from types import SimpleNamespace

from backend.services import signal_backtest_service


class _Result:
    def __init__(self, rows=None) -> None:
        self._rows = rows or []

    def all(self):
        return self._rows


class _CaptureDB:
    def __init__(self, rows=None) -> None:
        self.rows = rows or []
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(self.rows)


def test_signal_replay_formats_fractional_returns_as_percentages() -> None:
    rows = [
        SimpleNamespace(trade_date="2026-08-01", signal="Buy", raw_return=0.05),
        SimpleNamespace(trade_date="2026-07-01", signal="Buy", raw_return=-0.01),
    ]

    rendered = signal_backtest_service.render_signal_replay("AAPL", rows)

    assert "avg realized return +2.00%" in rendered
    assert "win rate 50%" in rendered
    assert "2026-08-01: Buy -> +5.00%" in rendered
    assert "2026-07-01: Buy -> -1.00%" in rendered


async def test_signal_replay_query_selects_only_scalar_replay_fields() -> None:
    db = _CaptureDB()

    await signal_backtest_service.get_signal_replay_context(db, "AAPL", 7)

    sql = str(db.statements[0].compile(compile_kwargs={"literal_binds": True})).lower()
    select_clause = sql.split(" from ", 1)[0]
    assert "analysis_results.trade_date" in select_clause
    assert "analysis_results.signal" in select_clause
    assert "analysis_results.raw_return" in select_clause
    assert "analysis_results.market_report" not in select_clause
    assert "analysis_results.portfolio_decision_json" not in select_clause
    assert "analysis_results.risk_debate_history" not in select_clause
