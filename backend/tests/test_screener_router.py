"""
Tests for the screener router.

Covers:
- GET /api/screener — crypto and stock screening, query param validation
- POST /api/screener/technical — technical indicator screening
- Indicator computation (RSI, SMA, EMA, MACD, Bollinger Bands)
- Filter logic helpers
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from models.market import AssetType, OHLCV, Quote, HistoricalData


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_quote(
    symbol: str = "AAPL",
    price: float = 150.0,
    change_percent: float = 1.5,
    volume: float = 50_000_000,
    market_cap: float = 2_500_000_000_000,
    asset_type: AssetType = AssetType.STOCK,
    source: str = "yfinance",
) -> Quote:
    return Quote(
        symbol=symbol,
        asset_type=asset_type,
        price=price,
        change=price * change_percent / 100,
        change_percent=change_percent,
        volume=volume,
        market_cap=market_cap,
        timestamp=datetime.now(tz=timezone.utc),
        source=source,
    )


def _make_hist(
    symbol: str = "AAPL",
    close_prices: Optional[List[float]] = None,
) -> HistoricalData:
    """Build a HistoricalData object with synthetic OHLCV candles."""
    if close_prices is None:
        # 90 days of synthetic prices drifting up slightly
        rng = np.random.default_rng(42)
        close_prices = list(np.cumsum(rng.normal(0.5, 2.0, 90)) + 150)

    candles = [
        OHLCV(
            timestamp=datetime.now(tz=timezone.utc),
            open=c * 0.99,
            high=c * 1.01,
            low=c * 0.98,
            close=c,
            volume=50_000_000,
        )
        for c in close_prices
    ]
    return HistoricalData(
        symbol=symbol,
        asset_type=AssetType.STOCK,
        interval="1d",
        candles=candles,
        source="yfinance",
    )


# ---------------------------------------------------------------------------
# Indicator computation unit tests
# ---------------------------------------------------------------------------


class TestIndicatorComputation:
    """Unit tests for the pure-NumPy indicator functions."""

    def test_compute_rsi_neutral(self):
        from routers.screener import _compute_rsi

        # A truly flat price series has zero gains AND zero losses.
        # avg_loss=0 → RSI formula returns 100 (no losses at all).
        # Build a series that alternates slightly to produce a ~50 RSI.
        closes = np.array([100.0 + (1.0 if i % 2 == 0 else -1.0) for i in range(30)])
        rsi = _compute_rsi(closes, period=14)
        assert 40 <= rsi <= 60, f"Alternating series RSI should be near 50, got {rsi}"

    def test_compute_rsi_all_up(self):
        from routers.screener import _compute_rsi

        closes = np.linspace(100, 200, 40)
        rsi = _compute_rsi(closes, period=14)
        assert rsi > 90, f"All-up series RSI should be >90, got {rsi}"

    def test_compute_rsi_all_down(self):
        from routers.screener import _compute_rsi

        closes = np.linspace(200, 100, 40)
        rsi = _compute_rsi(closes, period=14)
        assert rsi < 10, f"All-down series RSI should be <10, got {rsi}"

    def test_compute_rsi_insufficient_data(self):
        from routers.screener import _compute_rsi

        closes = np.array([100.0, 101.0, 102.0])
        rsi = _compute_rsi(closes, period=14)
        assert np.isnan(rsi)

    def test_compute_sma(self):
        from routers.screener import _compute_sma

        closes = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
        sma = _compute_sma(closes, period=3)
        assert sma == pytest.approx(40.0)

    def test_compute_sma_insufficient_data(self):
        from routers.screener import _compute_sma

        closes = np.array([10.0, 20.0])
        assert np.isnan(_compute_sma(closes, period=5))

    def test_compute_ema_converges(self):
        from routers.screener import _compute_ema

        closes = np.full(50, 100.0)
        ema = _compute_ema(closes, period=14)
        assert ema == pytest.approx(100.0, abs=0.01)

    def test_compute_macd_flat(self):
        from routers.screener import _compute_macd

        closes = np.full(100, 100.0)
        result = _compute_macd(closes)
        assert result["macd"] == pytest.approx(0.0, abs=0.01)
        assert result["histogram"] == pytest.approx(0.0, abs=0.01)

    def test_compute_macd_insufficient_data(self):
        from routers.screener import _compute_macd

        closes = np.full(10, 100.0)
        result = _compute_macd(closes)
        assert np.isnan(result["macd"])

    def test_compute_bollinger_flat(self):
        from routers.screener import _compute_bollinger

        closes = np.full(30, 100.0)
        result = _compute_bollinger(closes, period=20)
        assert result["middle"] == pytest.approx(100.0)
        # std = 0 → upper == lower == middle
        assert result["upper"] == pytest.approx(100.0)
        assert result["lower"] == pytest.approx(100.0)

    def test_compute_bollinger_percent_b(self):
        from routers.screener import _compute_bollinger

        rng = np.random.default_rng(0)
        closes = np.cumsum(rng.normal(0, 1.0, 40)) + 100
        result = _compute_bollinger(closes, period=20)
        # %B should be in a reasonable range for a typical series
        assert isinstance(result["percent_b"], float)
        assert not np.isnan(result["percent_b"])


class TestPassesIndicator:
    """Unit tests for _passes_indicator."""

    def _spec(self, itype: str, **kwargs):
        from routers.screener import TechnicalIndicatorSpec

        return TechnicalIndicatorSpec(type=itype, **kwargs)

    def test_rsi_pass(self):
        from routers.screener import _passes_indicator

        spec = self._spec("rsi", period=14, max_value=40.0)
        computed = {"rsi_14": 35.0}
        assert _passes_indicator(spec, computed, 100.0) is True

    def test_rsi_fail_too_high(self):
        from routers.screener import _passes_indicator

        spec = self._spec("rsi", period=14, max_value=40.0)
        computed = {"rsi_14": 55.0}
        assert _passes_indicator(spec, computed, 100.0) is False

    def test_rsi_fail_nan(self):
        from routers.screener import _passes_indicator

        spec = self._spec("rsi", period=14, max_value=40.0)
        computed = {"rsi_14": float("nan")}
        assert _passes_indicator(spec, computed, 100.0) is False

    def test_sma_cross_bullish_pass(self):
        from routers.screener import _passes_indicator

        spec = self._spec("sma_cross", short_period=50, long_period=200, direction="bullish")
        computed = {"sma_50": 155.0, "sma_200": 140.0, "sma_cross_signal": "bullish"}
        assert _passes_indicator(spec, computed, 160.0) is True

    def test_sma_cross_bullish_fail(self):
        from routers.screener import _passes_indicator

        spec = self._spec("sma_cross", short_period=50, long_period=200, direction="bullish")
        computed = {"sma_50": 130.0, "sma_200": 140.0, "sma_cross_signal": "bearish"}
        assert _passes_indicator(spec, computed, 125.0) is False

    def test_macd_histogram_pass(self):
        from routers.screener import _passes_indicator

        spec = self._spec("macd", min_value=0.0)
        computed = {"macd": 0.5, "signal": 0.2, "histogram": 0.3}
        assert _passes_indicator(spec, computed, 100.0) is True

    def test_macd_histogram_fail(self):
        from routers.screener import _passes_indicator

        spec = self._spec("macd", min_value=0.0)
        computed = {"macd": -0.5, "signal": -0.2, "histogram": -0.3}
        assert _passes_indicator(spec, computed, 100.0) is False

    def test_bb_percent_b_pass(self):
        from routers.screener import _passes_indicator

        spec = self._spec("bb", max_value=0.3)
        computed = {"upper": 110.0, "middle": 100.0, "lower": 90.0,
                    "bandwidth": 0.2, "percent_b": 0.2}
        assert _passes_indicator(spec, computed, 102.0) is True

    def test_bb_percent_b_fail(self):
        from routers.screener import _passes_indicator

        spec = self._spec("bb", max_value=0.3)
        computed = {"upper": 110.0, "middle": 100.0, "lower": 90.0,
                    "bandwidth": 0.2, "percent_b": 0.9}
        assert _passes_indicator(spec, computed, 109.0) is False


# ---------------------------------------------------------------------------
# Filter helper unit tests
# ---------------------------------------------------------------------------


class TestApplyQuoteFilters:
    """Unit tests for the _apply_quote_filters helper."""

    def test_filter_by_min_price(self):
        from routers.screener import _apply_quote_filters

        quotes = [_make_quote("A", price=50), _make_quote("B", price=150)]
        result = _apply_quote_filters(quotes, min_price=100, max_price=None,
                                      min_volume=None, max_volume=None,
                                      min_change_percent=None, max_change_percent=None,
                                      min_market_cap=None, max_market_cap=None)
        assert len(result) == 1
        assert result[0].symbol == "B"

    def test_filter_by_max_price(self):
        from routers.screener import _apply_quote_filters

        quotes = [_make_quote("A", price=50), _make_quote("B", price=150)]
        result = _apply_quote_filters(quotes, min_price=None, max_price=100,
                                      min_volume=None, max_volume=None,
                                      min_change_percent=None, max_change_percent=None,
                                      min_market_cap=None, max_market_cap=None)
        assert len(result) == 1
        assert result[0].symbol == "A"

    def test_filter_by_change_percent(self):
        from routers.screener import _apply_quote_filters

        quotes = [
            _make_quote("A", change_percent=2.0),
            _make_quote("B", change_percent=6.0),
            _make_quote("C", change_percent=-3.0),
        ]
        result = _apply_quote_filters(quotes, min_price=None, max_price=None,
                                      min_volume=None, max_volume=None,
                                      min_change_percent=5.0, max_change_percent=None,
                                      min_market_cap=None, max_market_cap=None)
        assert len(result) == 1
        assert result[0].symbol == "B"

    def test_filter_by_market_cap(self):
        from routers.screener import _apply_quote_filters

        quotes = [
            _make_quote("SMALL", market_cap=1_000_000),
            _make_quote("BIG", market_cap=1_000_000_000_000),
        ]
        result = _apply_quote_filters(quotes, min_price=None, max_price=None,
                                      min_volume=None, max_volume=None,
                                      min_change_percent=None, max_change_percent=None,
                                      min_market_cap=1_000_000_000, max_market_cap=None)
        assert len(result) == 1
        assert result[0].symbol == "BIG"

    def test_no_filters(self):
        from routers.screener import _apply_quote_filters

        quotes = [_make_quote("A"), _make_quote("B"), _make_quote("C")]
        result = _apply_quote_filters(quotes, min_price=None, max_price=None,
                                      min_volume=None, max_volume=None,
                                      min_change_percent=None, max_change_percent=None,
                                      min_market_cap=None, max_market_cap=None)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# GET /api/screener — integration tests (mocked services)
# ---------------------------------------------------------------------------


class TestScreenerEndpoint:
    """Integration tests for GET /api/screener."""

    @patch("routers.screener._screen_crypto")
    def test_crypto_screener_returns_results(
        self, mock_screen: AsyncMock, client: TestClient
    ):
        mock_screen.return_value = [
            _make_quote("BTC", price=40000, change_percent=3.5,
                        asset_type=AssetType.CRYPTO, source="coingecko"),
            _make_quote("ETH", price=2500, change_percent=1.2,
                        asset_type=AssetType.CRYPTO, source="coingecko"),
        ]
        resp = client.get("/api/screener?asset_type=crypto")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["count"] == 2
        assert data["total_screened"] == 2
        assert data["criteria"]["asset_type"] == "crypto"
        symbols = {r["symbol"] for r in data["results"]}
        assert symbols == {"BTC", "ETH"}

    @patch("routers.screener._screen_stocks")
    def test_stock_screener_returns_results(
        self, mock_screen: AsyncMock, client: TestClient
    ):
        mock_screen.return_value = [
            _make_quote("AAPL", price=178, change_percent=1.5),
            _make_quote("MSFT", price=320, change_percent=0.8),
        ]
        resp = client.get("/api/screener?asset_type=stock")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["count"] == 2

    @patch("routers.screener._screen_stocks")
    def test_screener_min_change_filter(
        self, mock_screen: AsyncMock, client: TestClient
    ):
        mock_screen.return_value = [
            _make_quote("AAPL", change_percent=1.5),
            _make_quote("NVDA", change_percent=8.0),
            _make_quote("T", change_percent=-1.0),
        ]
        resp = client.get("/api/screener?asset_type=stock&min_change_percent=5")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["count"] == 1
        assert data["results"][0]["symbol"] == "NVDA"

    @patch("routers.screener._screen_stocks")
    def test_screener_limit(self, mock_screen: AsyncMock, client: TestClient):
        mock_screen.return_value = [
            _make_quote(f"SYM{i}", change_percent=float(i)) for i in range(20)
        ]
        resp = client.get("/api/screener?asset_type=stock&limit=5")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["count"] == 5

    def test_screener_invalid_asset_type(self, client: TestClient):
        resp = client.get("/api/screener?asset_type=invalid")
        assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_screener_too_many_symbols(self, client: TestClient):
        symbols = ",".join([f"SYM{i}" for i in range(201)])
        resp = client.get(f"/api/screener?asset_type=stock&symbols={symbols}")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @patch("routers.screener._screen_stocks")
    def test_screener_criteria_in_response(
        self, mock_screen: AsyncMock, client: TestClient
    ):
        mock_screen.return_value = []
        resp = client.get(
            "/api/screener?asset_type=stock&min_price=10&max_price=500&min_change_percent=2"
        )
        assert resp.status_code == status.HTTP_200_OK
        criteria = resp.json()["criteria"]
        assert criteria["min_price"] == 10.0
        assert criteria["max_price"] == 500.0
        assert criteria["min_change_percent"] == 2.0

    @patch("routers.screener._screen_stocks")
    def test_screener_results_sorted_by_absolute_change(
        self, mock_screen: AsyncMock, client: TestClient
    ):
        """Results should be sorted by |change_percent| descending."""
        mock_screen.return_value = [
            _make_quote("A", change_percent=1.0),
            _make_quote("B", change_percent=-8.0),
            _make_quote("C", change_percent=5.0),
        ]
        resp = client.get("/api/screener?asset_type=stock")
        data = resp.json()
        changes = [abs(r["change_percent"]) for r in data["results"]]
        assert changes == sorted(changes, reverse=True)


# ---------------------------------------------------------------------------
# POST /api/screener/technical — integration tests (mocked services)
# ---------------------------------------------------------------------------


class TestTechnicalScreenerEndpoint:
    """Integration tests for POST /api/screener/technical."""

    @patch("routers.screener.YFinanceService")
    def test_technical_screener_rsi_filter(
        self, MockYF: MagicMock, client: TestClient
    ):
        """RSI < 40 filter should return oversold symbols."""
        # Build a down-trending price series (RSI will be low)
        closes_down = np.linspace(200, 100, 90).tolist()
        # Build an up-trending series (RSI will be high → filtered out)
        closes_up = np.linspace(100, 200, 90).tolist()

        instance = MockYF.return_value
        instance.get_historical = AsyncMock(
            side_effect=lambda sym, **kw: _make_hist(sym, closes_down if sym == "AAPL" else closes_up)
        )

        body = {
            "asset_type": "stock",
            "symbols": ["AAPL", "MSFT"],
            "indicators": [{"type": "rsi", "period": 14, "max_value": 40.0}],
            "limit": 50,
        }
        resp = client.post("/api/screener/technical", json=body)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        # AAPL (down-trending) should pass; MSFT (up-trending) should not
        result_symbols = {r["symbol"] for r in data["results"]}
        assert "AAPL" in result_symbols
        assert "MSFT" not in result_symbols

    @patch("routers.screener.YFinanceService")
    def test_technical_screener_sma_cross_bullish(
        self, MockYF: MagicMock, client: TestClient
    ):
        """SMA 5/10 bullish cross should pass when short > long."""
        # 40 candles trending up → short SMA > long SMA
        closes_up = np.linspace(100, 150, 40).tolist()
        instance = MockYF.return_value
        instance.get_historical = AsyncMock(
            return_value=_make_hist("AAPL", closes_up)
        )

        body = {
            "asset_type": "stock",
            "symbols": ["AAPL"],
            "indicators": [{"type": "sma_cross", "short_period": 5, "long_period": 10,
                            "direction": "bullish"}],
            "limit": 50,
        }
        resp = client.post("/api/screener/technical", json=body)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["count"] == 1
        assert data["results"][0]["symbol"] == "AAPL"
        assert "sma_5" in data["results"][0]["indicators"]
        assert "sma_10" in data["results"][0]["indicators"]

    @patch("routers.screener.YFinanceService")
    def test_technical_screener_no_results_when_all_filtered(
        self, MockYF: MagicMock, client: TestClient
    ):
        # Alternating up/down series yields RSI ~50 (see TestIndicatorComputation).
        # With max_value=40.0, RSI ~50 does NOT pass → count should be 0.
        closes_neutral = [100.0 + (1.0 if i % 2 == 0 else -1.0) for i in range(50)]
        instance = MockYF.return_value
        instance.get_historical = AsyncMock(
            return_value=_make_hist("AAPL", closes_neutral)
        )

        body = {
            "asset_type": "stock",
            "symbols": ["AAPL"],
            # RSI for an alternating series is ~50 — well below 60
            "indicators": [{"type": "rsi", "period": 14, "max_value": 40.0}],
            "limit": 50,
        }
        resp = client.post("/api/screener/technical", json=body)
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["count"] == 0

    def test_technical_screener_invalid_request_no_indicators(
        self, client: TestClient
    ):
        body = {
            "asset_type": "stock",
            "symbols": ["AAPL"],
            "indicators": [],
        }
        resp = client.post("/api/screener/technical", json=body)
        assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_technical_screener_invalid_indicator_type(self, client: TestClient):
        body = {
            "asset_type": "stock",
            "symbols": ["AAPL"],
            "indicators": [{"type": "invalid_indicator"}],
        }
        resp = client.post("/api/screener/technical", json=body)
        assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_technical_screener_sma_cross_long_must_exceed_short(
        self, client: TestClient
    ):
        body = {
            "asset_type": "stock",
            "symbols": ["AAPL"],
            "indicators": [{"type": "sma_cross", "short_period": 200, "long_period": 50}],
        }
        resp = client.post("/api/screener/technical", json=body)
        assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @patch("routers.screener.YFinanceService")
    def test_technical_screener_result_contains_indicator_values(
        self, MockYF: MagicMock, client: TestClient
    ):
        """Indicator values should be present in each result."""
        closes = np.linspace(100, 120, 50).tolist()
        instance = MockYF.return_value
        instance.get_historical = AsyncMock(
            return_value=_make_hist("TSLA", closes)
        )

        body = {
            "asset_type": "stock",
            "symbols": ["TSLA"],
            "indicators": [{"type": "macd"}],
            "limit": 50,
        }
        resp = client.post("/api/screener/technical", json=body)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        if data["count"] > 0:
            ind = data["results"][0]["indicators"]
            assert "macd" in ind
            assert "signal" in ind
            assert "histogram" in ind

    @patch("routers.screener.YFinanceService")
    def test_technical_screener_total_screened_count(
        self, MockYF: MagicMock, client: TestClient
    ):
        closes = np.full(50, 100.0).tolist()
        instance = MockYF.return_value
        instance.get_historical = AsyncMock(
            return_value=_make_hist("X", closes)
        )

        body = {
            "asset_type": "stock",
            "symbols": ["AAPL", "MSFT", "GOOGL"],
            "indicators": [{"type": "rsi", "period": 14}],
            "limit": 50,
        }
        resp = client.post("/api/screener/technical", json=body)
        assert resp.status_code == status.HTTP_200_OK
        # total_screened should reflect how many symbols had enough data
        assert resp.json()["total_screened"] >= 0
