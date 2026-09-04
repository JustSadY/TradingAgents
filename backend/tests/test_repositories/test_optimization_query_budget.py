from __future__ import annotations

from types import SimpleNamespace

from backend.repositories.optimization import list_optimization_runs


class _Mappings:
    def all(self):
        return []


class _Result:
    def mappings(self):
        return _Mappings()


class _CaptureDB:
    def __init__(self) -> None:
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result()


async def test_optimization_list_excludes_trial_history_column() -> None:
    db = _CaptureDB()
    user = SimpleNamespace(id=7, is_admin=False)

    rows = await list_optimization_runs(db, user, limit=20, offset=0)

    assert rows == []
    sql = str(db.statements[0].compile(compile_kwargs={"literal_binds": True})).lower()
    select_clause = sql.split(" from ", 1)[0]
    assert "optimization_runs.best_metrics" in select_clause
    assert "optimization_runs.trials " not in select_clause
    assert "optimization_runs.trials," not in select_clause
