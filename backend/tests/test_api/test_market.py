from __future__ import annotations

from httpx import AsyncClient


class TestMarketAPI:
    async def test_sentiment_history_returns_the_documented_object_shape(self, auth_client: AsyncClient, monkeypatch):
        async def fake_sentiment_history(db, ticker: str, user):
            assert ticker == "AAPL"
            assert user is not None
            return {
                "ticker": "AAPL",
                "history": [
                    {"time": "2026-07-18", "value": 0.5},
                    {"time": "2026-07-19", "value": -0.25},
                ],
            }

        monkeypatch.setattr("backend.api.market.get_sentiment_history", fake_sentiment_history)

        response = await auth_client.get("/api/market/sentiment-history", params={"ticker": "AAPL"})

        assert response.status_code == 200
        assert response.json() == {
            "ticker": "AAPL",
            "history": [
                {"time": "2026-07-18", "value": 0.5},
                {"time": "2026-07-19", "value": -0.25},
            ],
        }

    async def test_screener_response_preserves_its_public_metric_names(
        self, async_client: AsyncClient, admin_headers: dict[str, str], monkeypatch
    ):
        async def fake_run_screen(universe, top_n: int):
            assert universe == ["AAPL"]
            assert top_n == 1
            return [
                {
                    "ticker": "AAPL",
                    "score": 35.0,
                    "momentum_1m_pct": 12.4,
                    "trend": "above_sma50",
                    "volume_surge": 1.8,
                    "rsi_14": 58.2,
                    "signals": ["strong_momentum", "uptrend"],
                }
            ]

        monkeypatch.setattr("backend.api.screener.run_screen", fake_run_screen)
        async_client.headers.update(admin_headers)

        response = await async_client.post("/api/screener/scan", json={"tickers": ["AAPL"], "top_n": 1})

        assert response.status_code == 200
        assert response.json()["results"] == [
            {
                "ticker": "AAPL",
                "score": 35.0,
                "momentum_1m_pct": 12.4,
                "trend": "above_sma50",
                "volume_surge": 1.8,
                "rsi_14": 58.2,
                "signals": ["strong_momentum", "uptrend"],
            }
        ]
