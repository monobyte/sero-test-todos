"""
Tests for the quotes router.

Tests cover:
- Single quote endpoint (GET /api/quotes/{symbol})
- Batch quote endpoint (GET /api/quotes/batch)
- Fallback chain logic (primary → yfinance)
- Input validation (bad source, empty symbols, too many symbols)
- Error propagation (404 for unknown symbol, 429 rate limit, 503 all-failed)
"""
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from models.market import AssetType, Quote
from services.base import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    ServiceError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_quote(
    symbol: str = "AAPL",
    asset_type: AssetType = AssetType.STOCK,
    price: float = 150.25,
    source: str = "finnhub",
) -> Quote:
    return Quote(
        symbol=symbol,
        asset_type=asset_type,
        price=price,
        change=1.5,
        change_percent=1.0,
        volume=50_000_000.0,
        timestamp=datetime(2026, 3, 6, 14, 0, 0, tzinfo=timezone.utc),
        source=source,
    )


# ---------------------------------------------------------------------------
# Single-quote endpoint
# ---------------------------------------------------------------------------


class TestGetQuote:
    """Tests for GET /api/quotes/{symbol}."""

    def test_stock_quote_finnhub_success(self, client: TestClient):
        """Happy path: Finnhub returns a valid stock quote."""
        mock_quote = _make_quote("AAPL", AssetType.STOCK, source="finnhub")

        with patch("routers.quotes._get_finnhub") as mock_fn:
            mock_svc = MagicMock()
            mock_svc.get_quote = AsyncMock(return_value=mock_quote)
            mock_fn.return_value = mock_svc

            response = client.get("/api/quotes/AAPL")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "AAPL"
        assert data["price"] == 150.25
        assert data["source"] == "finnhub"

    def test_symbol_normalised_uppercase(self, client: TestClient):
        """Lowercase stock symbols are normalised to uppercase."""
        mock_quote = _make_quote("AAPL", AssetType.STOCK, source="finnhub")

        with patch("routers.quotes._get_finnhub") as mock_fn:
            mock_svc = MagicMock()
            mock_svc.get_quote = AsyncMock(return_value=mock_quote)
            mock_fn.return_value = mock_svc

            response = client.get("/api/quotes/aapl")

        assert response.status_code == 200

    def test_crypto_quote_coingecko_success(self, client: TestClient):
        """Happy path: CoinGecko returns a valid crypto quote."""
        mock_quote = _make_quote("BTC", AssetType.CRYPTO, price=42000.0, source="coingecko")

        with patch("routers.quotes._get_coingecko") as mock_fn:
            mock_svc = MagicMock()
            mock_svc.get_crypto_quote = AsyncMock(return_value=mock_quote)
            mock_fn.return_value = mock_svc

            response = client.get("/api/quotes/BTC")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "BTC"
        assert data["source"] == "coingecko"

    def test_stock_fallback_to_yfinance(self, client: TestClient):
        """When Finnhub fails, the router falls back to yfinance."""
        mock_quote = _make_quote("AAPL", AssetType.STOCK, source="yfinance")

        with (
            patch("routers.quotes._get_finnhub") as mock_finnhub,
            patch("routers.quotes._get_yfinance") as mock_yfinance,
        ):
            finnhub_svc = MagicMock()
            finnhub_svc.get_quote = AsyncMock(
                side_effect=ServiceError("Finnhub error", "finnhub")
            )
            mock_finnhub.return_value = finnhub_svc

            yfinance_svc = MagicMock()
            yfinance_svc.get_quote = AsyncMock(return_value=mock_quote)
            mock_yfinance.return_value = yfinance_svc

            response = client.get("/api/quotes/AAPL")

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "yfinance"

    def test_crypto_fallback_to_yfinance(self, client: TestClient):
        """When CoinGecko fails, the router falls back to yfinance."""
        mock_quote = _make_quote("BTC", AssetType.CRYPTO, source="yfinance")

        with (
            patch("routers.quotes._get_coingecko") as mock_cg,
            patch("routers.quotes._get_yfinance") as mock_yf,
        ):
            cg_svc = MagicMock()
            cg_svc.get_crypto_quote = AsyncMock(
                side_effect=RateLimitError("coingecko", retry_after=30)
            )
            mock_cg.return_value = cg_svc

            yf_svc = MagicMock()
            yf_svc.get_quote = AsyncMock(return_value=mock_quote)
            mock_yf.return_value = yf_svc

            response = client.get("/api/quotes/BTC")

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "yfinance"

    def test_stock_not_found_404(self, client: TestClient):
        """Unknown symbol → all sources return NotFoundError → 404."""
        with (
            patch("routers.quotes._get_finnhub") as mock_finnhub,
            patch("routers.quotes._get_yfinance") as mock_yfinance,
        ):
            finnhub_svc = MagicMock()
            finnhub_svc.get_quote = AsyncMock(
                side_effect=NotFoundError("finnhub", "INVALID_SYM")
            )
            mock_finnhub.return_value = finnhub_svc

            yf_svc = MagicMock()
            yf_svc.get_quote = AsyncMock(
                side_effect=NotFoundError("yfinance", "INVALID_SYM")
            )
            mock_yfinance.return_value = yf_svc

            response = client.get("/api/quotes/INVALID_SYM")

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "NotFound"

    def test_all_sources_fail_503(self, client: TestClient):
        """When all sources fail with service errors, respond with 503."""
        with (
            patch("routers.quotes._get_finnhub") as mock_finnhub,
            patch("routers.quotes._get_yfinance") as mock_yfinance,
        ):
            finnhub_svc = MagicMock()
            finnhub_svc.get_quote = AsyncMock(
                side_effect=ServiceError("Finnhub down", "finnhub")
            )
            mock_finnhub.return_value = finnhub_svc

            yf_svc = MagicMock()
            yf_svc.get_quote = AsyncMock(
                side_effect=ServiceError("yfinance down", "yfinance")
            )
            mock_yfinance.return_value = yf_svc

            response = client.get("/api/quotes/AAPL")

        assert response.status_code == 503

    def test_rate_limit_returns_429(self, client: TestClient):
        """When the pinned source is rate-limited, respond with 429."""
        with patch("routers.quotes._get_finnhub") as mock_finnhub:
            svc = MagicMock()
            svc.get_quote = AsyncMock(
                side_effect=RateLimitError("finnhub", retry_after=60)
            )
            mock_finnhub.return_value = svc

            response = client.get("/api/quotes/AAPL?source=finnhub")

        assert response.status_code == 429
        data = response.json()
        assert data["detail"]["error"] == "RateLimitExceeded"
        assert data["detail"]["detail"]["retry_after"] == 60

    def test_invalid_source_400(self, client: TestClient):
        """An unrecognised source query param returns 400."""
        response = client.get("/api/quotes/AAPL?source=badprovider")
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "ValidationError"

    def test_pinned_source_finnhub(self, client: TestClient):
        """When source=finnhub, only Finnhub is tried."""
        mock_quote = _make_quote("AAPL", source="finnhub")

        with (
            patch("routers.quotes._get_finnhub") as mock_finnhub,
            patch("routers.quotes._get_yfinance") as mock_yfinance,
        ):
            fh_svc = MagicMock()
            fh_svc.get_quote = AsyncMock(return_value=mock_quote)
            mock_finnhub.return_value = fh_svc

            yf_svc = MagicMock()
            yf_svc.get_quote = AsyncMock(return_value=_make_quote("AAPL", source="yfinance"))
            mock_yfinance.return_value = yf_svc

            response = client.get("/api/quotes/AAPL?source=finnhub")

        assert response.status_code == 200
        assert response.json()["source"] == "finnhub"
        # yfinance must NOT have been called
        yf_svc.get_quote.assert_not_called()

    def test_pinned_source_yfinance(self, client: TestClient):
        """When source=yfinance, only yfinance is tried."""
        mock_quote = _make_quote("AAPL", source="yfinance")

        with (
            patch("routers.quotes._get_finnhub") as mock_finnhub,
            patch("routers.quotes._get_yfinance") as mock_yfinance,
        ):
            fh_svc = MagicMock()
            fh_svc.get_quote = AsyncMock(return_value=_make_quote("AAPL", source="finnhub"))
            mock_finnhub.return_value = fh_svc

            yf_svc = MagicMock()
            yf_svc.get_quote = AsyncMock(return_value=mock_quote)
            mock_yfinance.return_value = yf_svc

            response = client.get("/api/quotes/AAPL?source=yfinance")

        assert response.status_code == 200
        assert response.json()["source"] == "yfinance"
        fh_svc.get_quote.assert_not_called()


# ---------------------------------------------------------------------------
# Batch quote endpoint
# ---------------------------------------------------------------------------


class TestGetBatchQuotes:
    """Tests for GET /api/quotes/batch."""

    def test_batch_success(self, client: TestClient):
        """Happy path: multiple symbols all succeed."""
        aapl = _make_quote("AAPL", source="finnhub")
        msft = _make_quote("MSFT", price=400.0, source="finnhub")

        with patch("routers.quotes._get_finnhub") as mock_fn:
            svc = MagicMock()
            svc.get_quote = AsyncMock(side_effect=[aapl, msft])
            mock_fn.return_value = svc

            response = client.get("/api/quotes/batch?symbols=AAPL,MSFT")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert data["failed_symbols"] == []
        assert len(data["quotes"]) == 2

    def test_batch_partial_failure(self, client: TestClient):
        """Partial failures: successful symbols returned, bad ones in failed_symbols."""
        aapl = _make_quote("AAPL", source="finnhub")

        with (
            patch("routers.quotes._get_finnhub") as mock_finnhub,
            patch("routers.quotes._get_yfinance") as mock_yfinance,
        ):
            fh_svc = MagicMock()
            fh_svc.get_quote = AsyncMock(side_effect=[
                aapl,
                NotFoundError("finnhub", "BADINPUT"),
            ])
            mock_finnhub.return_value = fh_svc

            yf_svc = MagicMock()
            yf_svc.get_quote = AsyncMock(
                side_effect=NotFoundError("yfinance", "BADINPUT")
            )
            mock_yfinance.return_value = yf_svc

            response = client.get("/api/quotes/batch?symbols=AAPL,BADINPUT")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert "BADINPUT" in data["failed_symbols"]
        assert len(data["quotes"]) == 1

    def test_batch_empty_symbols_400(self, client: TestClient):
        """Empty symbols string returns 400."""
        response = client.get("/api/quotes/batch?symbols=,,,")
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "ValidationError"

    def test_batch_too_many_symbols_400(self, client: TestClient):
        """More than 50 symbols returns 400."""
        symbols = ",".join(f"SYM{i}" for i in range(51))
        response = client.get(f"/api/quotes/batch?symbols={symbols}")
        assert response.status_code == 400
        data = response.json()
        assert "50" in data["detail"]["message"]

    def test_batch_deduplicate_symbols(self, client: TestClient):
        """Duplicate symbols are deduplicated before fetching."""
        mock_quote = _make_quote("AAPL", source="finnhub")

        with patch("routers.quotes._get_finnhub") as mock_fn:
            svc = MagicMock()
            svc.get_quote = AsyncMock(return_value=mock_quote)
            mock_fn.return_value = svc

            response = client.get("/api/quotes/batch?symbols=AAPL,AAPL,AAPL")

        assert response.status_code == 200
        data = response.json()
        # Should only call the service once
        assert data["count"] == 1

    def test_batch_invalid_source_400(self, client: TestClient):
        """An unrecognised source query param returns 400."""
        response = client.get("/api/quotes/batch?symbols=AAPL&source=invalid")
        assert response.status_code == 400

    def test_batch_response_has_timestamp(self, client: TestClient):
        """Batch response includes a timestamp field."""
        mock_quote = _make_quote("AAPL", source="finnhub")

        with patch("routers.quotes._get_finnhub") as mock_fn:
            svc = MagicMock()
            svc.get_quote = AsyncMock(return_value=mock_quote)
            mock_fn.return_value = svc

            response = client.get("/api/quotes/batch?symbols=AAPL")

        assert response.status_code == 200
        data = response.json()
        assert "timestamp" in data
        # Should be parseable as ISO datetime
        datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))

    def test_batch_missing_symbols_param_422(self, client: TestClient):
        """Missing required `symbols` query param returns 422."""
        response = client.get("/api/quotes/batch")
        assert response.status_code == 422
