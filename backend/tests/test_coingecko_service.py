"""
Tests for CoinGeckoService.

Covers:
- Symbol → CoinGecko ID resolution (static table + API search fallback)
- get_crypto_quote() — parses /coins/markets response into a Quote
- get_crypto_quotes_batch() — batch resolution and parsing
- get_trending() — parses /search/trending response
- get_top_coins() — /coins/markets with market cap ordering
- get_coin_market_data() — single-coin full market data
- get_global_market_data() — /global endpoint
- get_historical() — /coins/{id}/market_chart → HistoricalData
- get_ohlc() — /coins/{id}/ohlc → HistoricalData
- search_coins() — /search endpoint
- Error handling: 404, 401, 429, empty responses
- Caching: second call uses cache and skips HTTP
"""
import pytest
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from models.market import AssetType, Quote, HistoricalData
from services.coingecko_service import (
    CoinGeckoService,
    SYMBOL_TO_COINGECKO_ID,
)
from services.base import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    CacheType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_http_response(
    status_code: int,
    body: Any,
    headers: Dict[str, str] | None = None,
) -> MagicMock:
    """Build a mock httpx Response."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = body
    response.headers = headers or {}
    if status_code >= 400:
        http_err = httpx.HTTPStatusError(
            f"HTTP {status_code}",
            request=MagicMock(),
            response=response,
        )
        response.raise_for_status.side_effect = http_err
    else:
        response.raise_for_status.return_value = None
    return response


def _markets_item(
    coin_id: str = "bitcoin",
    symbol: str = "btc",
    name: str = "Bitcoin",
    price: float = 65_000.0,
    change_24h: float = 1_200.0,
    change_pct: float = 1.88,
    volume: float = 30_000_000_000.0,
    market_cap: float = 1_280_000_000_000.0,
    high_24h: float = 66_000.0,
    low_24h: float = 63_500.0,
) -> Dict[str, Any]:
    """Return a minimal /coins/markets list item."""
    return {
        "id": coin_id,
        "symbol": symbol,
        "name": name,
        "current_price": price,
        "market_cap": market_cap,
        "market_cap_rank": 1,
        "fully_diluted_valuation": 1_365_000_000_000.0,
        "total_volume": volume,
        "high_24h": high_24h,
        "low_24h": low_24h,
        "price_change_24h": change_24h,
        "price_change_percentage_24h": change_pct,
        "price_change_percentage_7d_in_currency": 4.5,
        "price_change_percentage_30d_in_currency": 12.1,
        "market_cap_change_24h": 25_000_000_000.0,
        "market_cap_change_percentage_24h": 2.0,
        "circulating_supply": 19_600_000.0,
        "total_supply": 21_000_000.0,
        "max_supply": 21_000_000.0,
        "ath": 73_750.0,
        "ath_change_percentage": -11.85,
        "ath_date": "2024-03-14T07:10:36.635Z",
        "atl": 67.81,
        "atl_change_percentage": 95714.27,
        "atl_date": "2013-07-06T00:00:00.000Z",
        "last_updated": "2026-03-06T17:00:00.000Z",
        "image": "https://assets.coingecko.com/coins/images/1/large/bitcoin.png",
    }


@pytest.fixture
def service():
    """CoinGeckoService instance with a cleared cache/rate limiter."""
    return CoinGeckoService()


# ---------------------------------------------------------------------------
# Symbol lookup table
# ---------------------------------------------------------------------------


class TestSymbolLookupTable:
    """Unit tests for the static SYMBOL_TO_COINGECKO_ID mapping."""

    def test_major_symbols_present(self):
        assert SYMBOL_TO_COINGECKO_ID["BTC"] == "bitcoin"
        assert SYMBOL_TO_COINGECKO_ID["ETH"] == "ethereum"
        assert SYMBOL_TO_COINGECKO_ID["SOL"] == "solana"
        assert SYMBOL_TO_COINGECKO_ID["USDT"] == "tether"
        assert SYMBOL_TO_COINGECKO_ID["DOGE"] == "dogecoin"

    def test_all_values_are_lowercase_strings(self):
        for symbol, coin_id in SYMBOL_TO_COINGECKO_ID.items():
            assert isinstance(coin_id, str), f"ID for {symbol} is not a string"
            assert coin_id == coin_id.lower(), f"ID for {symbol} is not lowercase"

    def test_all_keys_are_uppercase_strings(self):
        for symbol in SYMBOL_TO_COINGECKO_ID:
            assert symbol == symbol.upper(), f"Symbol {symbol} is not uppercase"

    def test_case_insensitive_lookup_via_service(self, service):
        assert service._symbol_to_id("btc") == "bitcoin"
        assert service._symbol_to_id("BTC") == "bitcoin"
        assert service._symbol_to_id("Btc") == "bitcoin"

    def test_unknown_symbol_returns_none(self, service):
        assert service._symbol_to_id("UNKNOWNCOIN") is None


# ---------------------------------------------------------------------------
# resolve_coin_id
# ---------------------------------------------------------------------------


class TestResolveCoinId:
    """Tests for the async resolve_coin_id method."""

    @pytest.mark.asyncio
    async def test_resolves_via_static_table(self, service):
        coin_id = await service.resolve_coin_id("BTC")
        assert coin_id == "bitcoin"

    @pytest.mark.asyncio
    async def test_resolves_case_insensitively(self, service):
        assert await service.resolve_coin_id("eth") == "ethereum"
        assert await service.resolve_coin_id("ETH") == "ethereum"

    @pytest.mark.asyncio
    async def test_passthrough_lowercase_id(self, service):
        """Symbols that look like CoinGecko IDs are returned as-is."""
        coin_id = await service.resolve_coin_id("bitcoin")
        assert coin_id == "bitcoin"

    @pytest.mark.asyncio
    async def test_api_search_fallback_exact_symbol_match(self, service):
        """Unknown symbols trigger /search and prefer exact symbol matches."""
        search_result = {
            "coins": [
                {"id": "wrong-coin", "symbol": "WRONG", "name": "Wrong Coin"},
                {"id": "myfaketoken", "symbol": "MFT", "name": "My Fake Token"},
            ]
        }
        mock_resp = _make_http_response(200, search_result)

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            coin_id = await service.resolve_coin_id("MFT")

        assert coin_id == "myfaketoken"
        await service.close()

    @pytest.mark.asyncio
    async def test_api_search_fallback_first_result(self, service):
        """Falls back to the first search result if no exact symbol match."""
        search_result = {
            "coins": [
                {"id": "some-token", "symbol": "SMT", "name": "Some Token"},
            ]
        }
        mock_resp = _make_http_response(200, search_result)

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            coin_id = await service.resolve_coin_id("NEWCOIN")

        assert coin_id == "some-token"
        await service.close()

    @pytest.mark.asyncio
    async def test_raises_not_found_when_search_empty(self, service):
        search_result = {"coins": []}
        mock_resp = _make_http_response(200, search_result)

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            with pytest.raises(NotFoundError) as exc_info:
                await service.resolve_coin_id("DOESNOTEXIST")

        assert "DOESNOTEXIST" in str(exc_info.value)
        await service.close()


# ---------------------------------------------------------------------------
# get_crypto_quote
# ---------------------------------------------------------------------------


class TestGetCryptoQuote:
    """Tests for get_crypto_quote()."""

    @pytest.mark.asyncio
    async def test_returns_quote_for_known_symbol(self, service):
        item = _markets_item()
        mock_resp = _make_http_response(200, [item])

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            quote = await service.get_crypto_quote("BTC")

        assert isinstance(quote, Quote)
        assert quote.symbol == "BTC"
        assert quote.asset_type == AssetType.CRYPTO
        assert quote.price == 65_000.0
        assert quote.change == 1_200.0
        assert quote.change_percent == 1.88
        assert quote.volume == 30_000_000_000.0
        assert quote.market_cap == 1_280_000_000_000.0
        assert quote.high_24h == 66_000.0
        assert quote.low_24h == 63_500.0
        assert quote.source == "coingecko"
        assert isinstance(quote.timestamp, datetime)
        await service.close()

    @pytest.mark.asyncio
    async def test_previous_close_derived_from_change(self, service):
        item = _markets_item(price=65_000.0, change_24h=1_200.0)
        mock_resp = _make_http_response(200, [item])

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            quote = await service.get_crypto_quote("BTC")

        assert quote.previous_close == pytest.approx(63_800.0, abs=1e-6)
        await service.close()

    @pytest.mark.asyncio
    async def test_open_price_is_none(self, service):
        """CoinGecko /coins/markets does not provide open price."""
        item = _markets_item()
        mock_resp = _make_http_response(200, [item])

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            quote = await service.get_crypto_quote("BTC")

        assert quote.open_price is None
        await service.close()

    @pytest.mark.asyncio
    async def test_raises_not_found_for_empty_response(self, service):
        mock_resp = _make_http_response(200, [])

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            with pytest.raises(NotFoundError):
                await service.get_crypto_quote("BTC")

        await service.close()

    @pytest.mark.asyncio
    async def test_handles_none_optional_fields(self, service):
        """Quote handles coins with missing optional market data gracefully."""
        item = _markets_item()
        item.update(
            {
                "total_volume": None,
                "market_cap": None,
                "high_24h": None,
                "low_24h": None,
            }
        )
        mock_resp = _make_http_response(200, [item])

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            quote = await service.get_crypto_quote("BTC")

        assert quote.volume is None
        assert quote.market_cap is None
        assert quote.high_24h is None
        assert quote.low_24h is None
        await service.close()

    @pytest.mark.asyncio
    async def test_uses_cache_on_second_call(self, service):
        """Second call for the same symbol must not make an HTTP request."""
        item = _markets_item()
        mock_resp = _make_http_response(200, [item])

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            await service.get_crypto_quote("BTC")
            await service.get_crypto_quote("BTC")  # should be cached
            assert mock_req.call_count == 1

        await service.close()

    @pytest.mark.asyncio
    async def test_authentication_error_on_401(self, service):
        mock_resp = _make_http_response(401, {"error": "Unauthorized"})

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            with pytest.raises(AuthenticationError):
                await service.get_crypto_quote("BTC")

        await service.close()

    @pytest.mark.asyncio
    async def test_rate_limit_error_on_429(self, service):
        mock_resp = _make_http_response(
            429, {"error": "Too Many Requests"}, headers={"Retry-After": "60"}
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch.object(
                httpx.AsyncClient,
                "request",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ):
                with pytest.raises(RateLimitError):
                    await service.get_crypto_quote("BTC")

        await service.close()


# ---------------------------------------------------------------------------
# get_crypto_quotes_batch
# ---------------------------------------------------------------------------


class TestGetCryptoQuotesBatch:
    """Tests for get_crypto_quotes_batch()."""

    @pytest.mark.asyncio
    async def test_returns_quotes_for_multiple_symbols(self, service):
        btc_item = _markets_item("bitcoin", "btc", "Bitcoin", price=65_000.0)
        eth_item = _markets_item("ethereum", "eth", "Ethereum", price=3_500.0)
        mock_resp = _make_http_response(200, [btc_item, eth_item])

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            quotes = await service.get_crypto_quotes_batch(["BTC", "ETH"])

        assert "BTC" in quotes
        assert "ETH" in quotes
        assert quotes["BTC"].price == 65_000.0
        assert quotes["ETH"].price == 3_500.0
        await service.close()

    @pytest.mark.asyncio
    async def test_skips_unknown_symbols(self, service):
        """Symbols not in the lookup table are silently skipped."""
        item = _markets_item()
        mock_resp = _make_http_response(200, [item])

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            quotes = await service.get_crypto_quotes_batch(["BTC", "UNKNOWNCOIN"])

        assert "BTC" in quotes
        assert "UNKNOWNCOIN" not in quotes
        await service.close()

    @pytest.mark.asyncio
    async def test_returns_empty_dict_for_all_unknown(self, service):
        quotes = await service.get_crypto_quotes_batch(["COIN_X", "COIN_Y"])
        assert quotes == {}


# ---------------------------------------------------------------------------
# get_trending
# ---------------------------------------------------------------------------


class TestGetTrending:
    """Tests for get_trending()."""

    @pytest.fixture
    def trending_response(self) -> Dict[str, Any]:
        return {
            "coins": [
                {
                    "item": {
                        "id": "bitcoin",
                        "name": "Bitcoin",
                        "symbol": "BTC",
                        "market_cap_rank": 1,
                        "thumb": "https://example.com/btc-thumb.png",
                        "large": "https://example.com/btc-large.png",
                        "score": 0,
                        "data": {
                            "price": 65000.0,
                            "price_change_percentage_24h": {"usd": 1.88},
                        },
                    }
                },
                {
                    "item": {
                        "id": "ethereum",
                        "name": "Ethereum",
                        "symbol": "ETH",
                        "market_cap_rank": 2,
                        "thumb": "https://example.com/eth-thumb.png",
                        "large": None,
                        "score": 1,
                        "data": {},
                    }
                },
            ],
            "nfts": [],
            "categories": [],
        }

    @pytest.mark.asyncio
    async def test_returns_list_of_trending_coins(self, service, trending_response):
        mock_resp = _make_http_response(200, trending_response)

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await service.get_trending()

        assert isinstance(result, list)
        assert len(result) == 2
        await service.close()

    @pytest.mark.asyncio
    async def test_trending_coin_structure(self, service, trending_response):
        mock_resp = _make_http_response(200, trending_response)

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await service.get_trending()

        btc = result[0]
        assert btc["id"] == "bitcoin"
        assert btc["name"] == "Bitcoin"
        assert btc["symbol"] == "BTC"  # always upper-cased
        assert btc["market_cap_rank"] == 1
        assert btc["score"] == 0
        assert btc["price_usd"] == 65000.0
        assert btc["price_change_24h_pct"] == 1.88
        await service.close()

    @pytest.mark.asyncio
    async def test_trending_symbol_is_uppercased(self, service, trending_response):
        # Make ETH symbol lowercase in raw data
        trending_response["coins"][1]["item"]["symbol"] = "eth"
        mock_resp = _make_http_response(200, trending_response)

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await service.get_trending()

        assert result[1]["symbol"] == "ETH"
        await service.close()

    @pytest.mark.asyncio
    async def test_empty_trending_response(self, service):
        mock_resp = _make_http_response(200, {"coins": [], "nfts": []})

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await service.get_trending()

        assert result == []
        await service.close()

    @pytest.mark.asyncio
    async def test_trending_uses_cache(self, service, trending_response):
        mock_resp = _make_http_response(200, trending_response)

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            await service.get_trending()
            await service.get_trending()
            assert mock_req.call_count == 1

        await service.close()


# ---------------------------------------------------------------------------
# get_top_coins / get_coin_market_data
# ---------------------------------------------------------------------------


class TestMarketCapData:
    """Tests for market cap retrieval methods."""

    @pytest.mark.asyncio
    async def test_get_top_coins_returns_list(self, service):
        items = [_markets_item("bitcoin", "btc"), _markets_item("ethereum", "eth")]
        mock_resp = _make_http_response(200, items)

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await service.get_top_coins(limit=2)

        assert isinstance(result, list)
        assert len(result) == 2
        await service.close()

    @pytest.mark.asyncio
    async def test_get_top_coins_dict_keys(self, service):
        item = _markets_item()
        mock_resp = _make_http_response(200, [item])

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await service.get_top_coins(limit=1)

        coin = result[0]
        assert coin["id"] == "bitcoin"
        assert coin["symbol"] == "BTC"
        assert coin["market_cap"] == 1_280_000_000_000.0
        assert coin["market_cap_rank"] == 1
        assert coin["current_price"] == 65_000.0
        assert coin["total_volume"] == 30_000_000_000.0
        await service.close()

    @pytest.mark.asyncio
    async def test_get_top_coins_limit_clamped(self, service):
        """Limit values outside 1-250 are clamped silently."""
        mock_resp = _make_http_response(200, [])

        with patch.object(
            httpx.AsyncClient,
            "request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_req:
            await service.get_top_coins(limit=9999)

        call_kwargs = mock_req.call_args.kwargs
        assert call_kwargs["params"]["per_page"] == 250
        await service.close()

    @pytest.mark.asyncio
    async def test_get_coin_market_data_structure(self, service):
        item = _markets_item()
        mock_resp = _make_http_response(200, [item])

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            data = await service.get_coin_market_data("BTC")

        expected_keys = {
            "id",
            "symbol",
            "name",
            "current_price",
            "market_cap",
            "market_cap_rank",
            "total_volume",
            "high_24h",
            "low_24h",
            "price_change_24h",
            "price_change_percentage_24h",
            "circulating_supply",
            "ath",
            "ath_change_percentage",
            "last_updated",
        }
        assert expected_keys.issubset(set(data.keys()))
        await service.close()

    @pytest.mark.asyncio
    async def test_get_coin_market_data_not_found(self, service):
        mock_resp = _make_http_response(200, [])

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            with pytest.raises(NotFoundError):
                await service.get_coin_market_data("BTC")

        await service.close()


# ---------------------------------------------------------------------------
# get_global_market_data
# ---------------------------------------------------------------------------


class TestGetGlobalMarketData:
    """Tests for get_global_market_data()."""

    @pytest.fixture
    def global_response(self) -> Dict[str, Any]:
        return {
            "data": {
                "active_cryptocurrencies": 12000,
                "markets": 750,
                "total_market_cap": {"usd": 2_500_000_000_000.0},
                "total_volume": {"usd": 120_000_000_000.0},
                "market_cap_percentage": {"btc": 52.3, "eth": 17.5},
                "market_cap_change_percentage_24h_usd": 1.2,
                "updated_at": 1741283400,
            }
        }

    @pytest.mark.asyncio
    async def test_returns_global_metrics(self, service, global_response):
        mock_resp = _make_http_response(200, global_response)

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            data = await service.get_global_market_data()

        assert data["total_market_cap_usd"] == 2_500_000_000_000.0
        assert data["total_24h_volume_usd"] == 120_000_000_000.0
        assert data["btc_dominance"] == 52.3
        assert data["eth_dominance"] == 17.5
        assert data["active_cryptocurrencies"] == 12000
        assert data["markets"] == 750
        await service.close()

    @pytest.mark.asyncio
    async def test_handles_missing_fields_gracefully(self, service):
        mock_resp = _make_http_response(200, {"data": {}})

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            data = await service.get_global_market_data()

        assert data["total_market_cap_usd"] is None
        assert data["btc_dominance"] is None
        await service.close()


# ---------------------------------------------------------------------------
# get_historical
# ---------------------------------------------------------------------------


class TestGetHistorical:
    """Tests for get_historical()."""

    @pytest.fixture
    def market_chart_response(self) -> Dict[str, Any]:
        """Minimal /market_chart response with 3 price+volume data points."""
        base_ts = 1_740_000_000_000  # ms
        return {
            "prices": [
                [base_ts, 60_000.0],
                [base_ts + 3_600_000, 61_000.0],
                [base_ts + 7_200_000, 62_000.0],
            ],
            "market_caps": [
                [base_ts, 1_200_000_000_000.0],
                [base_ts + 3_600_000, 1_210_000_000_000.0],
                [base_ts + 7_200_000, 1_220_000_000_000.0],
            ],
            "total_volumes": [
                [base_ts, 28_000_000_000.0],
                [base_ts + 3_600_000, 29_000_000_000.0],
                [base_ts + 7_200_000, 30_000_000_000.0],
            ],
        }

    @pytest.mark.asyncio
    async def test_returns_historical_data_object(self, service, market_chart_response):
        mock_resp = _make_http_response(200, market_chart_response)

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            hist = await service.get_historical("BTC", days=7)

        assert isinstance(hist, HistoricalData)
        assert hist.symbol == "BTC"
        assert hist.asset_type == AssetType.CRYPTO
        assert hist.source == "coingecko"
        await service.close()

    @pytest.mark.asyncio
    async def test_candle_count_matches_price_points(self, service, market_chart_response):
        mock_resp = _make_http_response(200, market_chart_response)

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            hist = await service.get_historical("BTC", days=7)

        assert len(hist.candles) == 3
        await service.close()

    @pytest.mark.asyncio
    async def test_candle_close_prices(self, service, market_chart_response):
        mock_resp = _make_http_response(200, market_chart_response)

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            hist = await service.get_historical("BTC", days=7)

        assert hist.candles[0].close == 60_000.0
        assert hist.candles[1].close == 61_000.0
        assert hist.candles[2].close == 62_000.0
        await service.close()

    @pytest.mark.asyncio
    async def test_candle_first_open_equals_close(self, service, market_chart_response):
        """First candle's open should equal its close (no prior close)."""
        mock_resp = _make_http_response(200, market_chart_response)

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            hist = await service.get_historical("BTC", days=7)

        assert hist.candles[0].open == hist.candles[0].close
        await service.close()

    @pytest.mark.asyncio
    async def test_candle_open_equals_previous_close(self, service, market_chart_response):
        """Candle open is derived from the previous candle's close."""
        mock_resp = _make_http_response(200, market_chart_response)

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            hist = await service.get_historical("BTC", days=7)

        assert hist.candles[1].open == 60_000.0  # = candles[0].close
        assert hist.candles[2].open == 61_000.0  # = candles[1].close
        await service.close()

    @pytest.mark.asyncio
    async def test_candle_volume_aligned_correctly(self, service, market_chart_response):
        mock_resp = _make_http_response(200, market_chart_response)

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            hist = await service.get_historical("BTC", days=7)

        assert hist.candles[0].volume == 28_000_000_000.0
        assert hist.candles[1].volume == 29_000_000_000.0
        await service.close()

    @pytest.mark.asyncio
    async def test_interval_label_for_one_day(self, service, market_chart_response):
        mock_resp = _make_http_response(200, market_chart_response)

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            hist = await service.get_historical("BTC", days=1)

        assert hist.interval == "5m"
        await service.close()

    @pytest.mark.asyncio
    async def test_interval_label_for_30_days(self, service, market_chart_response):
        mock_resp = _make_http_response(200, market_chart_response)

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            hist = await service.get_historical("BTC", days=30)

        assert hist.interval == "1h"
        await service.close()

    @pytest.mark.asyncio
    async def test_interval_label_for_365_days(self, service, market_chart_response):
        mock_resp = _make_http_response(200, market_chart_response)

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            hist = await service.get_historical("BTC", days=365)

        assert hist.interval == "1d"
        await service.close()

    @pytest.mark.asyncio
    async def test_empty_chart_returns_empty_candles(self, service):
        mock_resp = _make_http_response(
            200, {"prices": [], "market_caps": [], "total_volumes": []}
        )

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            hist = await service.get_historical("BTC", days=7)

        assert hist.candles == []
        await service.close()


# ---------------------------------------------------------------------------
# get_ohlc
# ---------------------------------------------------------------------------


class TestGetOhlc:
    """Tests for get_ohlc()."""

    @pytest.fixture
    def ohlc_response(self) -> list:
        base_ts = 1_740_000_000_000
        return [
            [base_ts, 60_000.0, 62_000.0, 59_500.0, 61_500.0],
            [base_ts + 14_400_000, 61_500.0, 63_000.0, 61_000.0, 62_000.0],
        ]

    @pytest.mark.asyncio
    async def test_returns_historical_data_with_ohlc(self, service, ohlc_response):
        mock_resp = _make_http_response(200, ohlc_response)

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            hist = await service.get_ohlc("BTC", days=7)

        assert isinstance(hist, HistoricalData)
        assert len(hist.candles) == 2
        await service.close()

    @pytest.mark.asyncio
    async def test_ohlc_values_parsed_correctly(self, service, ohlc_response):
        mock_resp = _make_http_response(200, ohlc_response)

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            hist = await service.get_ohlc("BTC", days=7)

        c = hist.candles[0]
        assert c.open == 60_000.0
        assert c.high == 62_000.0
        assert c.low == 59_500.0
        assert c.close == 61_500.0
        assert c.volume == 0.0  # not provided by OHLC endpoint
        await service.close()

    @pytest.mark.asyncio
    async def test_ohlc_days_snapped_to_valid_value(self, service, ohlc_response):
        """Days outside valid range are snapped to nearest valid value."""
        mock_resp = _make_http_response(200, ohlc_response)

        with patch.object(
            httpx.AsyncClient,
            "request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_req:
            await service.get_ohlc("BTC", days=45)  # snaps to 30

        call_kwargs = mock_req.call_args.kwargs
        assert call_kwargs["params"]["days"] == 30
        await service.close()


# ---------------------------------------------------------------------------
# search_coins
# ---------------------------------------------------------------------------


class TestSearchCoins:
    """Tests for search_coins()."""

    @pytest.mark.asyncio
    async def test_returns_normalised_results(self, service):
        search_body = {
            "coins": [
                {
                    "id": "bitcoin",
                    "name": "Bitcoin",
                    "symbol": "btc",
                    "market_cap_rank": 1,
                    "thumb": "https://example.com/btc.png",
                },
                {
                    "id": "bitcoin-cash",
                    "name": "Bitcoin Cash",
                    "symbol": "bch",
                    "market_cap_rank": 17,
                    "thumb": None,
                },
            ]
        }
        mock_resp = _make_http_response(200, search_body)

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            results = await service.search_coins("bitcoin")

        assert len(results) == 2
        assert results[0]["id"] == "bitcoin"
        assert results[0]["symbol"] == "BTC"  # upper-cased
        assert results[1]["symbol"] == "BCH"
        await service.close()

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_match(self, service):
        mock_resp = _make_http_response(200, {"coins": []})

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            results = await service.search_coins("xyznotacoin")

        assert results == []
        await service.close()


# ---------------------------------------------------------------------------
# Service configuration & header tests
# ---------------------------------------------------------------------------


class TestServiceConfiguration:
    """Tests for URL selection and header injection."""

    def test_service_name(self, service):
        assert service.SERVICE_NAME == "coingecko"

    def test_base_url_no_key(self):
        svc = CoinGeckoService()
        # With empty API key, use the public/demo URL
        with patch("config.settings.coingecko_api_key", ""):
            assert "api.coingecko.com" in svc._get_base_url()

    def test_demo_key_header(self):
        svc = CoinGeckoService()
        with patch("config.settings.coingecko_api_key", "demo_test_key_123"):
            headers = svc._get_default_headers()
        assert "x-cg-demo-api-key" in headers
        assert headers["x-cg-demo-api-key"] == "demo_test_key_123"

    def test_pro_key_header(self):
        svc = CoinGeckoService()
        with patch("config.settings.coingecko_api_key", "CG-prokey123"):
            headers = svc._get_default_headers()
        assert "x-cg-pro-api-key" in headers
        assert headers["x-cg-pro-api-key"] == "CG-prokey123"
        assert "x-cg-demo-api-key" not in headers

    def test_pro_key_uses_pro_base_url(self):
        svc = CoinGeckoService()
        with patch("config.settings.coingecko_api_key", "CG-prokey123"):
            url = svc._get_base_url()
        assert "pro-api.coingecko.com" in url

    def test_no_key_omits_auth_header(self):
        svc = CoinGeckoService()
        with patch("config.settings.coingecko_api_key", ""):
            headers = svc._get_default_headers()
        assert "x-cg-demo-api-key" not in headers
        assert "x-cg-pro-api-key" not in headers

    def test_user_agent_header_present(self, service):
        headers = service._get_default_headers()
        assert "User-Agent" in headers
        assert "MarketMonitor" in headers["User-Agent"]


# ---------------------------------------------------------------------------
# __init__.py exports
# ---------------------------------------------------------------------------


class TestExports:
    """Verify CoinGeckoService is exported from the services package."""

    def test_coingecko_service_importable_from_package(self):
        from services import CoinGeckoService as CG  # noqa: F401

        assert CG is CoinGeckoService

    def test_symbol_table_importable_from_package(self):
        from services import SYMBOL_TO_COINGECKO_ID as TABLE  # noqa: F401

        assert TABLE is SYMBOL_TO_COINGECKO_ID
