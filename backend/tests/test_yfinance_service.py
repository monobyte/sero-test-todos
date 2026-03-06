"""
Unit tests for YFinanceService.

Tests cover:
- Interval mapping and period resolution
- Historical data fetching (mocked yfinance)
- Quote fetching (mocked yfinance)
- Company info fetching (mocked yfinance)
- Caching behaviour
- Error handling (empty data, unknown symbols)
- Asset type detection
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pandas as pd

from models.market import AssetType, HistoricalData, Quote
from models.fundamental import CompanyProfile
from services.yfinance_service import YFinanceService, _INTERVAL_MAP, _VALID_PERIODS
from services.base import NotFoundError, ServiceError, CacheType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv_df(rows: int = 3) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame similar to yfinance output."""
    dates = pd.date_range("2026-01-01", periods=rows, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "Open":   [100.0 + i for i in range(rows)],
            "High":   [105.0 + i for i in range(rows)],
            "Low":    [95.0  + i for i in range(rows)],
            "Close":  [102.0 + i for i in range(rows)],
            "Volume": [1_000_000 * (i + 1) for i in range(rows)],
        },
        index=dates,
    )


def _make_ticker_mock(
    df: pd.DataFrame,
    fast_info: dict | None = None,
    info: dict | None = None,
) -> MagicMock:
    """Create a mock yfinance Ticker."""
    ticker = MagicMock()
    ticker.history.return_value = df
    # fast_info behaves like a dict for our _safe_float helper
    fi = MagicMock()
    fi_data = fast_info or {
        "lastPrice": 102.0,
        "previousClose": 100.0,
        "lastVolume": 1_000_000,
        "marketCap": 2_800_000_000_000.0,
        "dayHigh": 105.0,
        "dayLow": 95.0,
        "open": 100.5,
        "quoteType": "EQUITY",
    }
    fi.__getitem__ = lambda self, k: fi_data[k]
    fi.get = lambda k, default=None: fi_data.get(k, default)
    ticker.fast_info = fi
    ticker.info = info or {}
    return ticker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def svc() -> YFinanceService:
    """Fresh service instance with cleared state."""
    return YFinanceService()


# ---------------------------------------------------------------------------
# Static / unit tests (no I/O)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestIntervalMapping:
    """Verify interval string translation."""

    def test_known_intervals_mapped_correctly(self):
        assert _INTERVAL_MAP["1m"]  == "1m"
        assert _INTERVAL_MAP["5m"]  == "5m"
        assert _INTERVAL_MAP["15m"] == "15m"
        assert _INTERVAL_MAP["1h"]  == "1h"
        assert _INTERVAL_MAP["4h"]  == "1h"   # 4h falls back to 1h
        assert _INTERVAL_MAP["1d"]  == "1d"
        assert _INTERVAL_MAP["1w"]  == "1wk"
        assert _INTERVAL_MAP["1M"]  == "1mo"

    def test_map_interval_raises_on_unknown(self, svc):
        with pytest.raises(ServiceError, match="Unsupported interval"):
            svc._map_interval("3d")

    def test_valid_periods_set(self):
        for p in ("1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"):
            assert p in _VALID_PERIODS


@pytest.mark.unit
class TestPeriodResolution:
    """Verify period defaulting logic."""

    def test_valid_period_returned_unchanged(self, svc):
        assert svc._resolve_period("3mo", None) == "3mo"
        assert svc._resolve_period("1y", None)  == "1y"

    def test_invalid_period_falls_back_to_default(self, svc):
        result = svc._resolve_period("invalid_period", None)
        assert result == "1mo"  # _DEFAULT_PERIOD

    def test_none_period_falls_back_to_default(self, svc):
        assert svc._resolve_period(None, None) == "1mo"

    def test_start_overrides_period_not_matter(self, svc):
        # When start is given, period is irrelevant (won't be passed to yfinance)
        result = svc._resolve_period(None, "2026-01-01")
        assert result == "1mo"  # still returns default — caller controls via start kwarg


@pytest.mark.unit
class TestAssetTypeDetection:
    """Verify _detect_asset_type helper."""

    def _ticker_with_type(self, qtype: str) -> MagicMock:
        ticker = MagicMock()
        fi = MagicMock()
        fi.get = lambda k, default="": qtype if k == "quoteType" else default
        ticker.fast_info = fi
        return ticker

    def test_equity_maps_to_stock(self, svc):
        assert svc._detect_asset_type(self._ticker_with_type("EQUITY")) == AssetType.STOCK

    def test_etf_maps_to_etf(self, svc):
        assert svc._detect_asset_type(self._ticker_with_type("ETF")) == AssetType.ETF

    def test_cryptocurrency_maps_to_crypto(self, svc):
        assert svc._detect_asset_type(self._ticker_with_type("CRYPTOCURRENCY")) == AssetType.CRYPTO

    def test_index_maps_to_index(self, svc):
        assert svc._detect_asset_type(self._ticker_with_type("INDEX")) == AssetType.INDEX

    def test_unknown_defaults_to_stock(self, svc):
        assert svc._detect_asset_type(self._ticker_with_type("UNKNOWN")) == AssetType.STOCK

    def test_exception_in_fast_info_defaults_to_stock(self, svc):
        ticker = MagicMock()
        ticker.fast_info = MagicMock(side_effect=Exception("boom"))
        # _detect_asset_type catches the exception internally
        result = svc._detect_asset_type(ticker)
        assert result == AssetType.STOCK


@pytest.mark.unit
class TestSafeFloat:
    """Verify _safe_float helper."""

    def test_dict_key(self, svc):
        assert svc._safe_float({"price": 10.5}, "price") == 10.5

    def test_missing_key_returns_none(self, svc):
        assert svc._safe_float({}, "missing") is None

    def test_none_value_returns_none(self, svc):
        assert svc._safe_float({"x": None}, "x") is None

    def test_string_numeric_converted(self, svc):
        assert svc._safe_float({"x": "3.14"}, "x") == pytest.approx(3.14)

    def test_non_numeric_returns_none(self, svc):
        assert svc._safe_float({"x": "nan_str"}, "x") is None


# ---------------------------------------------------------------------------
# Async tests with mocked yfinance
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestGetHistorical:
    """Tests for YFinanceService.get_historical()."""

    @patch("services.yfinance_service.yf.Ticker")
    async def test_returns_historical_data(self, MockTicker, svc):
        df = _make_ohlcv_df(5)
        MockTicker.return_value = _make_ticker_mock(df)

        result = await svc.get_historical("AAPL", interval="1d", period="5d")

        assert isinstance(result, HistoricalData)
        assert result.symbol == "AAPL"
        assert result.interval == "1d"
        assert result.source == "yfinance"
        assert len(result.candles) == 5

    @patch("services.yfinance_service.yf.Ticker")
    async def test_candle_fields_populated(self, MockTicker, svc):
        df = _make_ohlcv_df(1)
        MockTicker.return_value = _make_ticker_mock(df)

        result = await svc.get_historical("AAPL")
        candle = result.candles[0]

        assert isinstance(candle.timestamp, datetime)
        assert candle.open  == 100.0
        assert candle.high  == 105.0
        assert candle.low   == 95.0
        assert candle.close == 102.0
        assert candle.volume == 1_000_000.0

    @patch("services.yfinance_service.yf.Ticker")
    async def test_interval_mapped_to_yfinance_string(self, MockTicker, svc):
        df = _make_ohlcv_df(3)
        ticker_mock = _make_ticker_mock(df)
        MockTicker.return_value = ticker_mock

        await svc.get_historical("AAPL", interval="1w")

        call_kwargs = ticker_mock.history.call_args[1]
        assert call_kwargs["interval"] == "1wk"

    @patch("services.yfinance_service.yf.Ticker")
    async def test_start_end_passed_through(self, MockTicker, svc):
        df = _make_ohlcv_df(3)
        ticker_mock = _make_ticker_mock(df)
        MockTicker.return_value = ticker_mock

        await svc.get_historical("AAPL", start="2025-01-01", end="2025-03-31")

        call_kwargs = ticker_mock.history.call_args[1]
        assert call_kwargs["start"] == "2025-01-01"
        assert call_kwargs["end"]   == "2025-03-31"
        assert "period" not in call_kwargs

    @patch("services.yfinance_service.yf.Ticker")
    async def test_empty_dataframe_raises_not_found(self, MockTicker, svc):
        MockTicker.return_value = _make_ticker_mock(pd.DataFrame())

        with pytest.raises(NotFoundError) as exc:
            await svc.get_historical("INVALID_SYM")

        assert exc.value.service == "yfinance"

    @patch("services.yfinance_service.yf.Ticker")
    async def test_result_cached_on_second_call(self, MockTicker, svc):
        df = _make_ohlcv_df(2)
        ticker_mock = _make_ticker_mock(df)
        MockTicker.return_value = ticker_mock

        result1 = await svc.get_historical("AAPL")
        result2 = await svc.get_historical("AAPL")

        # Second call should use cache — yf.Ticker called only once
        assert MockTicker.call_count == 1
        assert len(result1.candles) == len(result2.candles)

    @patch("services.yfinance_service.yf.Ticker")
    async def test_timezone_aware_timestamps_normalised(self, MockTicker, svc):
        """Timezone-aware Pandas timestamps must be converted to UTC-naive datetime."""
        df = _make_ohlcv_df(2)  # dates are tz-aware UTC in this helper
        MockTicker.return_value = _make_ticker_mock(df)

        result = await svc.get_historical("AAPL")
        for candle in result.candles:
            assert candle.timestamp.tzinfo is None  # must be tz-naive

    @patch("services.yfinance_service.yf.Ticker")
    async def test_yfinance_exception_wrapped_as_service_error(self, MockTicker, svc):
        ticker_mock = MagicMock()
        ticker_mock.history.side_effect = RuntimeError("Yahoo down")
        MockTicker.return_value = ticker_mock

        with pytest.raises(ServiceError, match="yfinance error"):
            await svc.get_historical("AAPL")


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetQuote:
    """Tests for YFinanceService.get_quote()."""

    @patch("services.yfinance_service.yf.Ticker")
    async def test_returns_quote_from_fast_info(self, MockTicker, svc):
        df = _make_ohlcv_df(0)  # empty — fast_info should supply price
        ticker_mock = _make_ticker_mock(df, fast_info={
            "lastPrice": 178.50,
            "previousClose": 175.00,
            "lastVolume": 50_000_000,
            "marketCap": 2.8e12,
            "dayHigh": 180.0,
            "dayLow": 175.0,
            "open": 176.0,
            "quoteType": "EQUITY",
        })
        MockTicker.return_value = ticker_mock

        result = await svc.get_quote("AAPL")

        assert isinstance(result, Quote)
        assert result.symbol    == "AAPL"
        assert result.price     == pytest.approx(178.50)
        assert result.source    == "yfinance"
        assert result.asset_type == AssetType.STOCK

    @patch("services.yfinance_service.yf.Ticker")
    async def test_falls_back_to_history_when_fast_info_missing_price(self, MockTicker, svc):
        df = _make_ohlcv_df(2)
        ticker_mock = _make_ticker_mock(df, fast_info={})
        # _safe_float on empty dict returns None → should fall back to history
        ticker_mock.fast_info.__getitem__ = MagicMock(side_effect=KeyError)
        MockTicker.return_value = ticker_mock

        result = await svc.get_quote("TSLA")

        assert result.price == pytest.approx(103.0)  # last row close value

    @patch("services.yfinance_service.yf.Ticker")
    async def test_change_and_change_pct_calculated(self, MockTicker, svc):
        fi = {
            "lastPrice": 110.0,
            "previousClose": 100.0,
            "lastVolume": 1_000,
            "marketCap": 1.0e9,
            "dayHigh": 115.0,
            "dayLow": 99.0,
            "open": 101.0,
            "quoteType": "EQUITY",
        }
        ticker_mock = _make_ticker_mock(_make_ohlcv_df(0), fast_info=fi)
        MockTicker.return_value = ticker_mock

        result = await svc.get_quote("XYZ")

        assert result.change         == pytest.approx(10.0, abs=0.001)
        assert result.change_percent == pytest.approx(10.0, abs=0.001)

    @patch("services.yfinance_service.yf.Ticker")
    async def test_empty_data_raises_not_found(self, MockTicker, svc):
        ticker_mock = MagicMock()
        ticker_mock.fast_info.__getitem__ = MagicMock(side_effect=KeyError)
        ticker_mock.history.return_value = pd.DataFrame()
        MockTicker.return_value = ticker_mock

        with pytest.raises(NotFoundError):
            await svc.get_quote("INVALID")

    @patch("services.yfinance_service.yf.Ticker")
    async def test_quote_is_cached(self, MockTicker, svc):
        fi = {"lastPrice": 50.0, "previousClose": 48.0, "quoteType": "EQUITY"}
        ticker_mock = _make_ticker_mock(_make_ohlcv_df(0), fast_info=fi)
        MockTicker.return_value = ticker_mock

        await svc.get_quote("MSFT")
        await svc.get_quote("MSFT")

        assert MockTicker.call_count == 1

    @patch("services.yfinance_service.yf.Ticker")
    async def test_symbol_is_upper_cased(self, MockTicker, svc):
        fi = {"lastPrice": 10.0, "previousClose": 9.0, "quoteType": "EQUITY"}
        ticker_mock = _make_ticker_mock(_make_ohlcv_df(0), fast_info=fi)
        MockTicker.return_value = ticker_mock

        await svc.get_quote("aapl")  # lowercase

        call_arg = MockTicker.call_args[0][0]
        assert call_arg == "AAPL"


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetCompanyInfo:
    """Tests for YFinanceService.get_company_info()."""

    _sample_info = {
        "symbol":               "AAPL",
        "longName":             "Apple Inc.",
        "exchange":             "NMS",
        "sector":               "Technology",
        "industry":             "Consumer Electronics",
        "longBusinessSummary":  "Apple Inc. designs ...",
        "website":              "https://www.apple.com",
        "country":              "United States",
        "fullTimeEmployees":    164000,
        "currency":             "USD",
        "marketCap":            2_800_000_000_000,
        "beta":                 1.23,
        "regularMarketPrice":   178.50,
        "averageVolume":        55_000_000,
        "quoteType":            "EQUITY",
    }

    @patch("services.yfinance_service.yf.Ticker")
    async def test_returns_company_profile(self, MockTicker, svc):
        ticker_mock = _make_ticker_mock(pd.DataFrame(), info=self._sample_info)
        MockTicker.return_value = ticker_mock

        profile = await svc.get_company_info("AAPL")

        assert isinstance(profile, CompanyProfile)
        assert profile.symbol       == "AAPL"
        assert profile.company_name == "Apple Inc."
        assert profile.sector       == "Technology"
        assert profile.is_etf       is False

    @patch("services.yfinance_service.yf.Ticker")
    async def test_etf_detected_from_quote_type(self, MockTicker, svc):
        info = {**self._sample_info, "quoteType": "ETF", "longName": "SPDR S&P 500 ETF"}
        ticker_mock = _make_ticker_mock(pd.DataFrame(), info=info)
        MockTicker.return_value = ticker_mock

        profile = await svc.get_company_info("SPY")

        assert profile.is_etf is True

    @patch("services.yfinance_service.yf.Ticker")
    async def test_result_cached_for_24h(self, MockTicker, svc):
        ticker_mock = _make_ticker_mock(pd.DataFrame(), info=self._sample_info)
        MockTicker.return_value = ticker_mock

        # Call twice — second should use cache
        await svc.get_company_info("AAPL")
        await svc.get_company_info("AAPL")

        assert MockTicker.call_count == 1

    @patch("services.yfinance_service.yf.Ticker")
    async def test_empty_info_raises_not_found(self, MockTicker, svc):
        ticker_mock = _make_ticker_mock(pd.DataFrame(), info={})
        MockTicker.return_value = ticker_mock

        with pytest.raises(NotFoundError):
            await svc.get_company_info("XXXXXX")


# ---------------------------------------------------------------------------
# Service configuration tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestServiceConfiguration:
    """Tests for service metadata and configuration."""

    def test_service_name(self, svc):
        assert svc.SERVICE_NAME == "yfinance"

    def test_base_url_is_empty(self, svc):
        assert svc._get_base_url() == ""

    def test_api_key_is_empty(self, svc):
        assert svc._get_api_key() == ""

    def test_max_retries(self, svc):
        assert svc.MAX_RETRIES == 2

    @pytest.mark.asyncio
    async def test_context_manager(self):
        async with YFinanceService() as svc_ctx:
            assert svc_ctx.SERVICE_NAME == "yfinance"
