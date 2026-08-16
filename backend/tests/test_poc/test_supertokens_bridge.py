"""The identity seam a SuperTokens migration would rest on.

These tests are the PoC's actual deliverable. Standing the core up and watching
a login succeed proves the easy half; what is in doubt is whether this
application's tenancy survives having its identity provider replaced, and that
is decided entirely by what happens between a verified session and
``set_config('app.user_id')``.

The RLS proof itself needs a real PostgreSQL and lives in
``test_supertokens_rls.py``. These are the rules around it.
"""

import pytest

from backend.poc.supertokens.bridge import (
    IdentityMappingError,
    parse_external_user_id,
    tenant_from_supertokens_session,
)


class _ContextSpy:
    """Records which RLS context the bridge asked for.

    The test suite runs on SQLite, where ``_apply_context`` returns before it
    records anything — so the values it would have sent to PostgreSQL are not
    observable on the session. Watching the call is.
    """

    def __init__(self):
        self.calls: list[tuple[str, int]] = []

    def install(self, monkeypatch):
        import backend.poc.supertokens.bridge as bridge

        async def tenant(_db, user_id):
            self.calls.append(("tenant", user_id))

        async def admin(_db, user_id):
            self.calls.append(("admin", user_id))

        monkeypatch.setattr(bridge, "set_request_tenant_context", tenant)
        monkeypatch.setattr(bridge, "set_request_admin_context", admin)
        return self


@pytest.fixture
def context_spy(monkeypatch):
    return _ContextSpy().install(monkeypatch)


def test_external_id_is_read_as_the_apps_integer_user_id():
    assert parse_external_user_id("41") == 41
    assert parse_external_user_id("  41  ") == 41


@pytest.mark.parametrize(
    "external_id",
    [
        None,
        "",
        "   ",
        # A SuperTokens user created without createUserIdMapping still has a
        # perfectly valid session; its id is just the internal UUID.
        "d7c3f1e2-9a4b-4c8d-8e1f-2b3a4c5d6e7f",
        "41; DROP TABLE users",
        "0",
        "-1",
    ],
)
def test_an_unmappable_session_is_refused_rather_than_run_without_a_tenant(external_id):
    """Failing open here would not be a lesser bug — it would be the worst one.

    An unset ``app.user_id`` is not "deny" under these policies. Every tenant
    table compares ``user_id`` against ``NULLIF('', '')::bigint``, so a request
    that reached the database with no context set would be evaluating NULL on
    every table at once rather than being blocked by name.
    """
    with pytest.raises(IdentityMappingError):
        parse_external_user_id(external_id)


async def test_a_normal_user_gets_a_tenant_context_for_its_own_id(db_session, test_user, context_spy):
    user = await tenant_from_supertokens_session(db_session, str(test_user.id))

    assert user.id == test_user.id
    assert context_spy.calls == [("tenant", test_user.id)]


async def test_admin_authority_comes_from_the_users_table_not_from_supertokens(
    db_session, admin_user, context_spy
):
    """``app.is_admin`` bypasses every tenant policy in the database.

    SuperTokens has a roles recipe, and it would be the natural place to put
    this. It must not be: the flag that disables row-level security across the
    whole schema has to be owned by the same database the policies are in.
    """
    user = await tenant_from_supertokens_session(db_session, str(admin_user.id))

    assert user.is_admin
    assert context_spy.calls == [("admin", admin_user.id)]


async def test_a_session_outliving_its_user_is_refused(db_session, test_user, context_spy):
    """The two-store consistency problem, in its smallest form.

    SuperTokens keeps its own user records. Deleting an application user does
    not delete the SuperTokens one, so a still-valid session can arrive for a
    ``users`` row that is gone. No context may be established for it.
    """
    missing_id = test_user.id + 10_000

    with pytest.raises(IdentityMappingError, match="no row in users"):
        await tenant_from_supertokens_session(db_session, str(missing_id))

    assert context_spy.calls == []


async def test_a_deactivated_user_is_refused(db_session, test_user, context_spy):
    test_user.is_active = False
    await db_session.flush()

    with pytest.raises(IdentityMappingError, match="deactivated"):
        await tenant_from_supertokens_session(db_session, str(test_user.id))

    assert context_spy.calls == []
