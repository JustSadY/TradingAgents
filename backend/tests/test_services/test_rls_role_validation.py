from backend.core.rls import rls_role_is_safe


def test_rls_role_is_safe_only_for_non_owner_non_bypass_role():
    assert rls_role_is_safe(is_superuser=False, bypass_rls=False, owned_rls_tables=0)
    assert not rls_role_is_safe(is_superuser=True, bypass_rls=False, owned_rls_tables=0)
    assert not rls_role_is_safe(is_superuser=False, bypass_rls=True, owned_rls_tables=0)
    assert not rls_role_is_safe(is_superuser=False, bypass_rls=False, owned_rls_tables=1)
