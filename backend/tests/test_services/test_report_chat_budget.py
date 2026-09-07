from __future__ import annotations

from types import SimpleNamespace

from backend.services import report_chat_service


class _ScalarResult:
    def __init__(self, value=None, rows=None) -> None:
        self._value = value
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _CaptureDB:
    def __init__(self, result) -> None:
        self.result = result
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return self.result


async def test_owned_report_query_loads_only_chat_report_surface() -> None:
    db = _CaptureDB(_ScalarResult(value=SimpleNamespace()))
    user = SimpleNamespace(id=7, is_admin=False)

    await report_chat_service._get_owned_analysis(db, 12, user)

    sql = str(db.statements[0].compile(compile_kwargs={"literal_binds": True})).lower()
    assert "market_report" in sql
    assert "final_decision" in sql
    assert "risk_debate_history" not in sql
    assert "strategy_after_json" not in sql
    assert "tokens_in" not in sql


async def test_prompt_history_query_is_bounded_to_recent_messages() -> None:
    db = _CaptureDB(_ScalarResult(rows=[]))

    await report_chat_service._list_prompt_history(db, 12)

    sql = str(db.statements[0].compile(compile_kwargs={"literal_binds": True})).upper()
    assert "ORDER BY ANALYSIS_CHATS.CREATED_AT DESC" in sql
    assert f"LIMIT {report_chat_service._MAX_PROMPT_HISTORY_MESSAGES}" in sql
