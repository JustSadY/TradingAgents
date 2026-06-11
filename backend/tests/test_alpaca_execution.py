from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.execution.alpaca import AlpacaTrader
from backend.services.execution.base import OrderRequest
from backend.services.execution.factory import get_trader


@pytest.mark.asyncio
async def test_alpaca_trader_init_and_url():
    # Test simulation mode URL
    trader_sim = AlpacaTrader(mode="simulation")
    assert trader_sim.mode == "simulation"
    assert trader_sim.base_url == "https://paper-api.alpaca.markets"

    # Test live mode URL
    trader_live = AlpacaTrader(mode="live")
    assert trader_live.mode == "live"
    assert trader_live.base_url == "https://api.alpaca.markets"


@pytest.mark.asyncio
async def test_alpaca_trader_get_credentials():
    db_mock = AsyncMock()
    user_mock = MagicMock()
    user_mock.role = "owner"

    # Mock db execution to return a mock owner user
    scalar_mock = MagicMock()
    scalar_mock.scalar_one_or_none.return_value = user_mock
    db_mock.execute.return_value = scalar_mock

    trader = AlpacaTrader(db=db_mock)

    with patch("backend.services.user_service.get_user_api_key") as mock_get_key, \
         patch("backend.core.config.get_settings") as mock_get_settings:

        mock_get_settings.return_value.get_fernet.return_value = "fake_fernet"
        mock_get_key.side_effect = lambda user, provider, fernet: f"decrypted_{provider}"

        key, secret = await trader._get_credentials()
        assert key == "decrypted_alpaca_key"
        assert secret == "decrypted_alpaca_secret"


@pytest.mark.asyncio
@patch("httpx.AsyncClient.get")
@patch("httpx.AsyncClient.post")
async def test_alpaca_trader_place_order_success(mock_post, mock_get):
    db_mock = AsyncMock()
    trader = AlpacaTrader(db=db_mock, mode="simulation")

    # Mock credentials method
    trader._get_credentials = AsyncMock(return_value=("key_123", "sec_456"))

    # Mock immediate filled response from Alpaca
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "ord_999",
        "status": "filled",
        "filled_avg_price": "180.50",
        "filled_qty": "10.0"
    }
    mock_post.return_value = mock_resp

    # Mock GET response if polling happens (though immediate parsing should break out)
    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.json.return_value = {
        "id": "ord_999",
        "status": "filled",
        "filled_avg_price": "180.50",
        "filled_qty": "10.0"
    }
    mock_get.return_value = mock_get_resp

    req = OrderRequest(
        ticker="AAPL",
        action="BUY",
        quantity=10.0,
        reference_price=180.0,
        stop_loss=170.0,
        take_profit=200.0
    )

    res = await trader.place_order(req)
    assert res.order_id == "ord_999"
    assert res.status == "FILLED"
    assert res.filled_price == 180.50
    assert res.filled_quantity == 10.0

    # Verify mock POST call carries bracket fields
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    posted_body = kwargs["json"]
    assert posted_body["symbol"] == "AAPL"
    assert posted_body["order_class"] == "bracket"
    assert posted_body["take_profit"]["limit_price"] == "200.00"
    assert posted_body["stop_loss"]["stop_price"] == "170.00"


@pytest.mark.asyncio
async def test_factory_resolves_alpaca():
    trader = get_trader(mode="simulation", broker="alpaca")
    assert isinstance(trader, AlpacaTrader)
    assert trader.mode == "simulation"

    trader_live = get_trader(mode="live", broker="alpaca")
    assert isinstance(trader_live, AlpacaTrader)
    assert trader_live.mode == "live"
