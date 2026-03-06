"""
Tests for the historical data router.

Tests cover:
- GET /api/historical/{symbol} happy paths for stocks and crypto
- Fallback chains (Finnhub → yfinance, CoinGecko → yfinance)
- Input validation (interval, source, date range)
- Limit / candle trimming
- Error responses (404, 429, 503)
"""
from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from models.market import OHLCV, AssetType, HistoricalData
from services.base import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    ServiceError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candle(days_ago: int = 0) -> OHLCV:
    # Use a fixed base date and subtract using timedelta to avoid day-of-month overflow
    from datetime import timedelta
    base = datetime(2026, 3, 6, tzinfo=timezone.utc)
    ts = base - timedelta(days=days_ago)
    return OHLCV(
        timestamp=ts,
        open=148.0,
        high=151.0,
        low=147.0,
        close=150.0,
        volume=50_000_000.0,
    )


def _make_historical(
    symbol: str = "AAPL",
    asset_type: AssetType = AssetType.STOCK,
    interval: str = "1d",
    source: str = "finnhub",
    candle_count: int = 3,
) -> HistoricalData:
    return HistoricalData(
        symbol=symbol,
        asset_type=asset_type,
        interval=interval,
        candles=[_make_candle(i) for i in range(candle_count - 1, -1, -1)],
        source=source,
    )


# ---------------------------------------------------------------------------
# Stock historical tests
# ---------------------------------------------------------------------------


class TestGetHistoricalStock:
    """Tests for stock historical data via Finnhub → yfinance fallback."""

    def test_stock_historical_finnhub_success(self, client: TestClient):
        """Happy path: Finnhub returns valid candle data."""
        mock_data = _make_historical("AAPL", source="finnhub", candle_count=5)

        with patch("routers.historical._get_finnhub") as mock_fn:
            svc = MagicMock()
            svc.get_candles = AsyncMock(return_value=mock_data)
            mock_fn.return_value = svc

            response = client.get("/api/historical/AAPL?interval=1d")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "AAPL"
        assert data["interval"] == "1d"
        assert data["source"] == "finnhub"
        assert data["count"] == 5
        assert len(data["candles"]) == 5

    def test_stock_historical_fallback_to_yfinance(self, client: TestClient):
        """Finnhub failure triggers fallback to yfinance."""
        mock_data = _make_historical("AAPL", source="yfinance", candle_count=3)

        with (
            patch("routers.historical._get_finnhub") as mock_fh,
            patch("routers.historical._get_yfinance") as mock_yf,
        ):
            fh_svc = MagicMock()
            fh_svc.get_candles = AsyncMock(
                side_effect=ServiceError("Finnhub error", "finnhub")
            )
            mock_fh.return_value = fh_svc

            yf_svc = MagicMock()
            yf_svc.get_historical = AsyncMock(return_value=mock_data)
            mock_yf.return_value = yf_svc

            response = client.get("/api/historical/AAPL?interval=1d")

        assert response.status_code == 200
        assert response.json()["source"] == "yfinance"

    def test_stock_historical_not_found_404(self, client: TestClient):
        """Unknown symbol → all sources return NotFoundError → 404."""
        with (
            patch("routers.historical._get_finnhub") as mock_fh,
            patch("routers.historical._get_yfinance") as mock_yf,
        ):
            fh_svc = MagicMock()
            fh_svc.get_candles = AsyncMock(
                side_effect=NotFoundError("finnhub", "INVALID")
            )
            mock_fh.return_value = fh_svc

            yf_svc = MagicMock()
            yf_svc.get_historical = AsyncMock(
                side_effect=NotFoundError("yfinance", "INVALID")
            )
            mock_yf.return_value = yf_svc

            response = client.get("/api/historical/INVALID?interval=1d")

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "NotFound"

    def test_rate_limit_on_pinned_source_429(self, client: TestClient):
        """Rate limit on pinned source → 429."""
        with patch("routers.historical._get_finnhub") as mock_fn:
            svc = MagicMock()
            svc.get_candles = AsyncMock(
                side_effect=RateLimitError("finnhub", retry_after=60)
            )
            mock_fn.return_value = svc

            response = client.get("/api/historical/AAPL?interval=1d&source=finnhub")

        assert response.status_code == 429

    def test_all_sources_fail_503(self, client: TestClient):
        """All sources fail → 503."""
        with (
            patch("routers.historical._get_finnhub") as mock_fh,
            patch("routers.historical._get_yfinance") as mock_yf,
        ):
            fh_svc = MagicMock()
            fh_svc.get_candles = AsyncMock(
                side_effect=ServiceError("down", "finnhub")
            )
            mock_fh.return_value = fh_svc

            yf_svc = MagicMock()
            yf_svc.get_historical = AsyncMock(
                side_effect=ServiceError("down", "yfinance")
            )
            mock_yf.return_value = yf_svc

            response = client.get("/api/historical/AAPL?interval=1d")

        assert response.status_code == 503


# ---------------------------------------------------------------------------
# Crypto historical tests
# ---------------------------------------------------------------------------


class TestGetHistoricalCrypto:
    """Tests for crypto historical data via CoinGecko → yfinance fallback."""

    def test_crypto_historical_coingecko_success(self, client: TestClient):
        """Happy path: CoinGecko returns valid candle data."""
        mock_data = _make_historical("BTC", AssetType.CRYPTO, source="coingecko")

        with patch("routers.historical._get_coingecko") as mock_fn:
            svc = MagicMock()
            svc.get_historical = AsyncMock(return_value=mock_data)
            mock_fn.return_value = svc

            response = client.get("/api/historical/BTC?interval=1d")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "BTC"
        assert data["source"] == "coingecko"
        assert data["asset_type"] == "crypto"

    def test_crypto_historical_fallback_to_yfinance(self, client: TestClient):
        """CoinGecko failure → yfinance fallback."""
        mock_data = _make_historical("BTC", AssetType.CRYPTO, source="yfinance")

        with (
            patch("routers.historical._get_coingecko") as mock_cg,
            patch("routers.historical._get_yfinance") as mock_yf,
        ):
            cg_svc = MagicMock()
            cg_svc.get_historical = AsyncMock(
                side_effect=RateLimitError("coingecko", retry_after=30)
            )
            mock_cg.return_value = cg_svc

            yf_svc = MagicMock()
            yf_svc.get_historical = AsyncMock(return_value=mock_data)
            mock_yf.return_value = yf_svc

            response = client.get("/api/historical/BTC?interval=1d")

        assert response.status_code == 200
        assert response.json()["source"] == "yfinance"


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestHistoricalValidation:
    """Input validation tests for GET /api/historical/{symbol}."""

    def test_invalid_interval_400(self, client: TestClient):
        """Unknown interval value returns 400."""
        response = client.get("/api/historical/AAPL?interval=bad")
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "ValidationError"
        assert "interval" in data["detail"]["detail"]["field"]

    def test_invalid_source_400(self, client: TestClient):
        """Unknown source value returns 400."""
        response = client.get("/api/historical/AAPL?source=badprovider")
        assert response.status_code == 400

    def test_from_date_after_to_date_400(self, client: TestClient):
        """from > to date range returns 400."""
        response = client.get(
            "/api/historical/AAPL?from=2026-03-01&to=2026-01-01"
        )
        assert response.status_code == 400
        data = response.json()
        assert "from" in data["detail"]["message"].lower()

    def test_invalid_date_format_400(self, client: TestClient):
        """Malformed date string returns 400."""
        response = client.get("/api/historical/AAPL?from=not-a-date")
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "ValidationError"

    @pytest.mark.parametrize("interval", ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"])
    def test_all_valid_intervals_accepted(self, client: TestClient, interval: str):
        """All documented interval values are accepted by the validator."""
        mock_data = _make_historical("AAPL", source="finnhub")

        with patch("routers.historical._get_finnhub") as mock_fn:
            svc = MagicMock()
            svc.get_candles = AsyncMock(return_value=mock_data)
            mock_fn.return_value = svc

            response = client.get(f"/api/historical/AAPL?interval={interval}")

        # We only check that the router accepted the interval (not 400)
        assert response.status_code != 400

    def test_limit_trims_candles(self, client: TestClient):
        """The limit parameter trims the candle list to the N most recent."""
        # Return 10 candles but request limit=3
        mock_data = _make_historical("AAPL", source="finnhub", candle_count=10)

        with patch("routers.historical._get_finnhub") as mock_fn:
            svc = MagicMock()
            svc.get_candles = AsyncMock(return_value=mock_data)
            mock_fn.return_value = svc

            response = client.get("/api/historical/AAPL?interval=1d&limit=3")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 3
        assert len(data["candles"]) == 3

    def test_limit_below_min_422(self, client: TestClient):
        """Limit < 1 returns FastAPI 422 validation error."""
        response = client.get("/api/historical/AAPL?limit=0")
        assert response.status_code == 422

    def test_limit_above_max_422(self, client: TestClient):
        """Limit > 5000 returns FastAPI 422 validation error."""
        response = client.get("/api/historical/AAPL?limit=9999")
        assert response.status_code == 422

    def test_date_range_passed_to_service(self, client: TestClient):
        """from/to dates are forwarded to Finnhub's get_candles."""
        mock_data = _make_historical("AAPL", source="finnhub")

        with patch("routers.historical._get_finnhub") as mock_fn:
            svc = MagicMock()
            svc.get_candles = AsyncMock(return_value=mock_data)
            mock_fn.return_value = svc

            response = client.get(
                "/api/historical/AAPL?interval=1d&from=2026-01-01&to=2026-03-01"
            )

        assert response.status_code == 200
        # Verify get_candles was called with non-None timestamps
        call_kwargs = svc.get_candles.call_args
        assert call_kwargs.kwargs.get("from_timestamp") is not None
        assert call_kwargs.kwargs.get("to_timestamp") is not None

    def test_response_includes_count(self, client: TestClient):
        """Response body includes a `count` field equal to len(candles)."""
        mock_data = _make_historical("AAPL", source="finnhub", candle_count=7)

        with patch("routers.historical._get_finnhub") as mock_fn:
            svc = MagicMock()
            svc.get_candles = AsyncMock(return_value=mock_data)
            mock_fn.return_value = svc

            response = client.get("/api/historical/AAPL")

        data = response.json()
        assert data["count"] == len(data["candles"]) == 7

    def test_pinned_source_yfinance_skips_finnhub(self, client: TestClient):
        """source=yfinance bypasses Finnhub entirely."""
        mock_data = _make_historical("AAPL", source="yfinance")

        with (
            patch("routers.historical._get_finnhub") as mock_fh,
            patch("routers.historical._get_yfinance") as mock_yf,
        ):
            fh_svc = MagicMock()
            fh_svc.get_candles = AsyncMock(return_value=mock_data)
            mock_fh.return_value = fh_svc

            yf_svc = MagicMock()
            yf_svc.get_historical = AsyncMock(return_value=mock_data)
            mock_yf.return_value = yf_svc

            response = client.get("/api/historical/AAPL?source=yfinance")

        assert response.status_code == 200
        assert response.json()["source"] == "yfinance"
        fh_svc.get_candles.assert_not_called()
