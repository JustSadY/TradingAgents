from pathlib import Path


def test_backtest_service_does_not_own_analysis_sql() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    source = (backend_root / "services" / "backtest_service.py").read_text()

    assert "from sqlalchemy import select" not in source
    assert "backend.models.analysis" not in source
    assert "select(AnalysisResult" not in source
    assert "list_consensus_analyses" in source


def test_backtest_causal_filter_stays_in_service() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    source = (backend_root / "services" / "backtest_service.py").read_text()

    assert "excluded_created_after_trade_date" in source
    assert "pd.Timestamp(created_at).date() > pd.Timestamp(row.trade_date).date()" in source
