"""Exchange-holiday gating for scheduled scans and automated orders."""

from __future__ import annotations

from datetime import date

import pytest

from backend.services import market_calendar_service as mcal

# US Independence Day 2026 falls on a Saturday, so the NYSE observes it on the 3rd.
NYSE_HOLIDAY = date(2026, 7, 3)
NYSE_SESSION = date(2026, 7, 6)


class TestCalendarResolution:
    @pytest.mark.parametrize("ticker", ["BTC-USD", "ETH-USD", "SOLUSDT", "btc", "DOGE-EUR"])
    def test_crypto_has_no_exchange_calendar(self, ticker):
        assert mcal.calendar_code_for(ticker) is None

    def test_an_explicit_crypto_asset_type_wins_over_the_symbol(self):
        assert mcal.calendar_code_for("AAPL", asset_type="crypto") is None

    @pytest.mark.parametrize(
        ("ticker", "expected"),
        [
            ("AAPL", "XNYS"),
            ("THYAO.IS", "XIST"),
            ("VOD.L", "XLON"),
            ("SAP.DE", "XETR"),
            ("SHOP.TO", "XTSE"),
            ("7203.T", "XTKS"),
        ],
    )
    def test_a_venue_suffix_selects_that_exchange(self, ticker, expected):
        assert mcal.calendar_code_for(ticker) == expected

    def test_an_unknown_suffix_falls_back_to_the_default_equity_calendar(self):
        assert mcal.calendar_code_for("FOO.ZZZ") == "XNYS"


class TestTradingDay:
    def test_crypto_trades_on_every_calendar_day(self):
        assert mcal.is_trading_day(NYSE_HOLIDAY, ticker="BTC-USD") is True
        assert mcal.is_trading_day(date(2026, 12, 25), asset_type="crypto") is True

    def test_an_observed_holiday_is_not_a_session(self):
        assert mcal.is_trading_day(NYSE_HOLIDAY, ticker="AAPL") is False

    def test_a_weekend_is_not_a_session(self):
        assert mcal.is_trading_day(date(2026, 7, 5), ticker="AAPL") is False

    def test_an_ordinary_weekday_is_a_session(self):
        assert mcal.is_trading_day(NYSE_SESSION, ticker="AAPL") is True

    def test_exchanges_keep_their_own_holidays(self):
        """US Thanksgiving 2026 closes New York and leaves London trading."""
        thanksgiving = date(2026, 11, 26)
        assert mcal.is_trading_day(thanksgiving, ticker="AAPL") is False
        assert mcal.is_trading_day(thanksgiving, ticker="VOD.L") is True

    def test_an_unavailable_calendar_fails_open(self, monkeypatch):
        """A calendar problem must never freeze every user's automation."""
        monkeypatch.setattr(mcal, "_calendar", lambda code: None)
        assert mcal.is_trading_day(NYSE_HOLIDAY, ticker="AAPL") is True


class TestClosedReason:
    def test_a_session_produces_no_reason(self):
        assert mcal.market_closed_reason(NYSE_SESSION, ticker="AAPL") is None

    def test_a_holiday_names_the_exchange_and_the_next_session(self):
        reason = mcal.market_closed_reason(NYSE_HOLIDAY, ticker="AAPL")
        assert reason is not None
        assert "XNYS" in reason
        assert NYSE_SESSION.isoformat() in reason


class TestNextTradingDay:
    def test_a_session_returns_itself(self):
        assert mcal.next_trading_day(NYSE_SESSION, ticker="AAPL") == NYSE_SESSION

    def test_a_long_weekend_skips_to_the_following_session(self):
        assert mcal.next_trading_day(NYSE_HOLIDAY, ticker="AAPL") == NYSE_SESSION
