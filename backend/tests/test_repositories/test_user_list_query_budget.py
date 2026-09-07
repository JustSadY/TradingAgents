from __future__ import annotations

from backend.repositories.users import list_users


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


async def test_managed_user_list_excludes_credentials_and_api_keys() -> None:
    db = _CaptureDB()

    rows = await list_users(db)

    assert rows == []
    sql = str(db.statements[0].compile(compile_kwargs={"literal_binds": True})).lower()
    select_clause = sql.split(" from ", 1)[0]
    assert "users.username" in select_clause
    assert "users.email" in select_clause
    assert "users.role" in select_clause
    assert "users.hashed_password" not in select_clause
    assert "users.api_keys_enc" not in select_clause
    assert "users.token_version" not in select_clause
