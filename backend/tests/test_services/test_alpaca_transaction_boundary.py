from types import SimpleNamespace

import pytest


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _CredentialDb:
    def __init__(self, owner):
        self.owner = owner
        self.commits = 0

    async def execute(self, _statement):
        return _ScalarResult(self.owner)

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_alpaca_credentials_release_db_before_network_when_enabled(monkeypatch):
    from backend.core import config
    from backend.services import user_service
    from backend.services.execution.alpaca import AlpacaTrader

    owner = SimpleNamespace(id=1, role="owner", api_keys_enc="encrypted")
    db = _CredentialDb(owner)
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(get_fernet=lambda: object()))
    monkeypatch.setattr(
        user_service,
        "get_user_api_key",
        lambda _user, provider, _fernet: {
            "alpaca_key": "key",
            "alpaca_secret": "secret",
        }.get(provider),
    )

    trader = AlpacaTrader(db=db, mode="live", release_db_before_network=True)

    assert await trader._get_credentials() == ("key", "secret")
    assert db.commits == 1


@pytest.mark.asyncio
async def test_direct_alpaca_trader_keeps_manual_transaction_control_by_default(monkeypatch):
    from backend.core import config
    from backend.services import user_service
    from backend.services.execution.alpaca import AlpacaTrader

    owner = SimpleNamespace(id=1, role="owner", api_keys_enc="encrypted")
    db = _CredentialDb(owner)
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(get_fernet=lambda: object()))
    monkeypatch.setattr(user_service, "get_user_api_key", lambda _user, _provider, _fernet: "credential")

    trader = AlpacaTrader(db=db, mode="live")

    await trader._get_credentials()
    assert db.commits == 0


def test_execution_factory_enables_alpaca_network_boundary():
    from backend.services.execution.factory import get_trader

    trader = get_trader(mode="live", broker="alpaca", db=object())

    assert trader._release_db_before_network is True
