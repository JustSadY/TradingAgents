from pathlib import Path


def test_trading_orchestrator_does_not_own_broker_audit_sql_or_orm_rows() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    source = (backend_root / "services" / "trading_orchestrator.py").read_text()

    assert "from sqlalchemy import select" not in source
    assert "backend.models.portfolio" not in source
    assert "backend.models.order" not in source
    assert "select(Portfolio" not in source
    assert "Portfolio(" not in source
    assert "Order(" not in source
    assert "db.add(" not in source
    assert "await db.flush()" not in source
    assert "backend.repositories.trading_execution" in source
    assert "_repo_get_or_create_broker_audit_portfolio" in source
    assert "_repo_persist_broker_order" in source
    assert "_repo_apply_broker_account_balances" in source
