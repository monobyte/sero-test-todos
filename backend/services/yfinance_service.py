"""
YFinance service for historical OHLCV data and basic stock quotes.

yfinance wraps Yahoo Finance and provides:
- Historical OHLCV candles (primary use case)
- Basic real-time / delayed quotes
- Company information

NOTE: yfinance is a third-party library that reverse-engineers Yahoo Finance's
unofficial API. It has no API key requirement and imposes no hard rate limits,
but aggressive usage can trigger temporary IP bans. We rely on the cache layer
to minimise raw calls.

IMPORTANT: yfinance is a *synchronous* library. All calls are dispatched to a
thread-pool executor via asyncio.get_event_loop().run_in_executor() so that the
async FastAPI event loop is never blocked.

INTERVAL SUPPORT:
-----------------
yfinance supports a subset of intervals. The mapping from our API intervals:

  Our API    yfinance    Max lookback
  --------   --------    ------------
  1m         1m          7 days
  5m         5m          60 days
  15m        15m         60 days
  1h         1h          730 days
  4h         (not native; falls back to 1h with a note)
  1d         1d          unlimited
  1w         1wk         unlimited
  1M         1mo         unlimited

VALID PERIOD VALUES (if not using start/end):
  1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
"""
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import yfinance as yf

from models.fundamental import CompanyProfile
from models.market import AssetType, HistoricalData, OHLCV, Quote
from services.base import BaseService, CacheType, NotFoundError, ServiceError
from utils.logger import get_logger

logger = get_logger(__name__)

# Map our canonical interval names to yfinance interval strings
_INTERVAL_MAP: Dict[str, str] = {
    "1m": "1m",
    "2m": "2m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "1h",  # yfinance has no native 4h; fall back to 1h
    "1d": "1d",
    "1w": "1wk",
    "1M": "1mo",
}

# Valid yfinance period strings (used when start/end are not provided)
_VALID_PERIODS = frozenset(
    {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}
)

_DEFAULT_PERIOD = "1mo"


class YFinanceService(BaseService):
    """
    Service for fetching historical and quote data via the yfinance library.

    Acts as a fallback provider for historical OHLCV data when Finnhub's
    historical endpoint is unavailable or rate-limited.

    Usage::

        async with YFinanceService() as svc:
            data = await svc.get_historical("AAPL", interval="1d", period="3mo")
            quote = await svc.get_quote("AAPL")
    """

    SERVICE_NAME = "yfinance"

    # yfinance has no hard rate limit, but we keep a conservative ceiling to
    # avoid Yahoo Finance throttling the container's IP address.
    MAX_RETRIES = 2
    RETRY_BACKOFF_FACTOR = 2.0
    REQUEST_TIMEOUT = 45.0  # yfinance calls can be slow

    # ------------------------------------------------------------------ #
    # BaseService abstract method implementations                          #
    # ------------------------------------------------------------------ #

    def _get_base_url(self) -> str:
        """Not used — yfinance is a library, not an HTTP service."""
        return ""

    def _get_api_key(self) -> str:
        """No API key required for yfinance."""
        return ""

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    async def get_historical(
        self,
        symbol: str,
        interval: str = "1d",
        period: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> HistoricalData:
        """
        Fetch historical OHLCV candles for a symbol.

        Args:
            symbol:   Ticker symbol (e.g. "AAPL", "TSLA").
            interval: Candle interval — one of "1m", "5m", "15m", "1h",
                      "4h", "1d", "1w", "1M" (default "1d").
            period:   Lookback period string — one of "1d", "5d", "1mo",
                      "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max".
                      Ignored when *start* is provided (default "1mo").
            start:    ISO 8601 date/datetime string for range start.
                      Overrides *period* when supplied.
            end:      ISO 8601 date/datetime string for range end.
                      Defaults to today when *start* is provided.

        Returns:
            HistoricalData with OHLCV candles.

        Raises:
            NotFoundError: Symbol not found or no data returned.
            ServiceError:  yfinance internal error.
        """
        symbol = symbol.upper()
        yf_interval = self._map_interval(interval)
        effective_period = self._resolve_period(period, start)

        # Build a deterministic cache key
        cache_key = self._build_cache_key(
            "historical",
            symbol,
            yf_interval,
            start or effective_period,
            end or "",
        )
        cached = self._get_cached(CacheType.HISTORICAL, cache_key)
        if cached is not None:
            self._logger.debug(
                "cache_hit",
                service=self.SERVICE_NAME,
                symbol=symbol,
                interval=interval,
            )
            return HistoricalData(**cached)

        # Rate-limit check
        self._check_rate_limit()

        # Offload blocking yfinance I/O to a thread
        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(
                None,
                lambda: self._fetch_historical_sync(
                    symbol, yf_interval, effective_period, start, end
                ),
            )
        except (NotFoundError, ServiceError):
            raise
        except Exception as exc:
            self._logger.error(
                "yfinance_error",
                service=self.SERVICE_NAME,
                symbol=symbol,
                error=str(exc),
            )
            raise ServiceError(
                message=f"yfinance error fetching historical data for {symbol}: {exc}",
                service=self.SERVICE_NAME,
            ) from exc

        self._record_call()
        self._logger.info(
            "historical_fetched",
            service=self.SERVICE_NAME,
            symbol=symbol,
            interval=interval,
            candles=len(data.candles),
        )

        # Persist to cache (using model_dump for JSON serialisation)
        self._set_cached(CacheType.HISTORICAL, cache_key, data.model_dump(mode="json"))
        return data

    async def get_quote(self, symbol: str) -> Quote:
        """
        Fetch a basic (delayed) stock quote using yfinance.

        Derived from the most-recent daily candle and ``fast_info`` where
        available. Not a substitute for a real-time feed (Finnhub is
        preferred for live quotes), but useful as a fallback.

        Args:
            symbol: Ticker symbol (e.g. "AAPL").

        Returns:
            Quote object with price and basic market data.

        Raises:
            NotFoundError: Symbol not found or no data returned.
            ServiceError:  yfinance internal error.
        """
        symbol = symbol.upper()

        cache_key = self._build_cache_key("quote", symbol)
        cached = self._get_cached(CacheType.QUOTE, cache_key)
        if cached is not None:
            self._logger.debug(
                "cache_hit",
                service=self.SERVICE_NAME,
                symbol=symbol,
            )
            return Quote(**cached)

        self._check_rate_limit()

        loop = asyncio.get_event_loop()
        try:
            quote = await loop.run_in_executor(
                None,
                lambda: self._fetch_quote_sync(symbol),
            )
        except (NotFoundError, ServiceError):
            raise
        except Exception as exc:
            self._logger.error(
                "yfinance_error",
                service=self.SERVICE_NAME,
                symbol=symbol,
                error=str(exc),
            )
            raise ServiceError(
                message=f"yfinance error fetching quote for {symbol}: {exc}",
                service=self.SERVICE_NAME,
            ) from exc

        self._record_call()
        self._logger.info(
            "quote_fetched",
            service=self.SERVICE_NAME,
            symbol=symbol,
            price=quote.price,
        )

        self._set_cached(CacheType.QUOTE, cache_key, quote.model_dump(mode="json"))
        return quote

    async def get_company_info(self, symbol: str) -> CompanyProfile:
        """
        Fetch basic company profile information via yfinance.

        Uses ``ticker.info`` which returns a rich metadata dictionary from
        Yahoo Finance. Cached for 24 hours (fundamental TTL).

        Args:
            symbol: Ticker symbol (e.g. "AAPL").

        Returns:
            CompanyProfile with available fields populated.

        Raises:
            NotFoundError: Symbol not found.
            ServiceError:  yfinance internal error.
        """
        symbol = symbol.upper()

        cache_key = self._build_cache_key("info", symbol)
        cached = self._get_cached(CacheType.FUNDAMENTAL, cache_key)
        if cached is not None:
            self._logger.debug(
                "cache_hit",
                service=self.SERVICE_NAME,
                symbol=symbol,
            )
            return CompanyProfile(**cached)

        self._check_rate_limit()

        loop = asyncio.get_event_loop()
        try:
            profile = await loop.run_in_executor(
                None,
                lambda: self._fetch_info_sync(symbol),
            )
        except (NotFoundError, ServiceError):
            raise
        except Exception as exc:
            self._logger.error(
                "yfinance_error",
                service=self.SERVICE_NAME,
                symbol=symbol,
                error=str(exc),
            )
            raise ServiceError(
                message=f"yfinance error fetching company info for {symbol}: {exc}",
                service=self.SERVICE_NAME,
            ) from exc

        self._record_call()

        self._set_cached(CacheType.FUNDAMENTAL, cache_key, profile.model_dump(mode="json"))
        return profile

    # ------------------------------------------------------------------ #
    # Synchronous helpers (run inside executor)                            #
    # ------------------------------------------------------------------ #

    def _fetch_historical_sync(
        self,
        symbol: str,
        yf_interval: str,
        period: str,
        start: Optional[str],
        end: Optional[str],
    ) -> HistoricalData:
        """
        Blocking call to yfinance — must run in an executor thread.

        Args:
            symbol:      Ticker symbol (already upper-cased).
            yf_interval: yfinance interval string (e.g. "1d", "1h").
            period:      Lookback period (used when start is None).
            start:       Start date string or None.
            end:         End date string or None.

        Returns:
            HistoricalData populated from the DataFrame.

        Raises:
            NotFoundError: Empty DataFrame (symbol not found / no data).
        """
        ticker = yf.Ticker(symbol)

        # Build kwargs — start/end take precedence over period
        kwargs: Dict[str, Any] = {"interval": yf_interval, "auto_adjust": True}
        if start:
            kwargs["start"] = start
            if end:
                kwargs["end"] = end
        else:
            kwargs["period"] = period

        df = ticker.history(**kwargs)

        if df is None or df.empty:
            raise NotFoundError(
                self.SERVICE_NAME,
                symbol,
                message=(
                    f"No historical data returned for '{symbol}' "
                    f"(interval={yf_interval}, period={period}). "
                    "Symbol may be invalid or data unavailable for this range."
                ),
            )

        candles: List[OHLCV] = []
        for ts, row in df.iterrows():
            # yfinance timestamps may be tz-aware; normalise to UTC-naive
            if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
                ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
            else:
                ts = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts

            candles.append(
                OHLCV(
                    timestamp=ts,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row.get("Volume", 0.0)),
                )
            )

        # Detect asset type from quoteType in fast_info where possible
        asset_type = self._detect_asset_type(ticker)

        return HistoricalData(
            symbol=symbol,
            asset_type=asset_type,
            interval=yf_interval,
            candles=candles,
            source=self.SERVICE_NAME,
        )

    def _fetch_quote_sync(self, symbol: str) -> Quote:
        """
        Blocking call to build a Quote from yfinance fast_info + recent history.

        fast_info is a lightweight, less data-intensive way to get the latest
        price; it falls back to the most-recent daily candle if unavailable.

        Args:
            symbol: Ticker symbol (already upper-cased).

        Returns:
            Quote model.

        Raises:
            NotFoundError: No price data available.
        """
        ticker = yf.Ticker(symbol)
        fi = ticker.fast_info

        # Try to get price from fast_info; keys may be absent for some symbols
        price: Optional[float] = None
        prev_close: Optional[float] = None
        volume: Optional[float] = None
        market_cap: Optional[float] = None
        day_high: Optional[float] = None
        day_low: Optional[float] = None
        open_price: Optional[float] = None

        try:
            price = self._safe_float(fi, "lastPrice")
            prev_close = self._safe_float(fi, "previousClose") or self._safe_float(
                fi, "regularMarketPreviousClose"
            )
            volume = self._safe_float(fi, "lastVolume")
            market_cap = self._safe_float(fi, "marketCap")
            day_high = self._safe_float(fi, "dayHigh")
            day_low = self._safe_float(fi, "dayLow")
            open_price = self._safe_float(fi, "open")
        except Exception:
            pass  # fast_info can raise on missing data

        # Fallback: pull from most-recent daily candle
        if price is None:
            df = ticker.history(period="2d", interval="1d", auto_adjust=True)
            if df is None or df.empty:
                raise NotFoundError(
                    self.SERVICE_NAME,
                    symbol,
                    message=f"No price data available for '{symbol}'.",
                )
            latest = df.iloc[-1]
            price = float(latest["Close"])
            day_high = day_high or float(latest["High"])
            day_low = day_low or float(latest["Low"])
            open_price = open_price or float(latest["Open"])
            volume = volume or float(latest.get("Volume", 0.0))
            if len(df) >= 2:
                prev_close = prev_close or float(df.iloc[-2]["Close"])

        if price is None:
            raise NotFoundError(
                self.SERVICE_NAME,
                symbol,
                message=f"No price data available for '{symbol}'.",
            )

        prev_close = prev_close or 0.0
        change = price - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0.0

        asset_type = self._detect_asset_type(ticker)

        return Quote(
            symbol=symbol,
            asset_type=asset_type,
            price=price,
            change=round(change, 4),
            change_percent=round(change_pct, 4),
            volume=volume,
            market_cap=market_cap,
            high_24h=day_high,
            low_24h=day_low,
            open_price=open_price,
            previous_close=prev_close if prev_close else None,
            timestamp=datetime.utcnow(),
            source=self.SERVICE_NAME,
        )

    def _fetch_info_sync(self, symbol: str) -> CompanyProfile:
        """
        Blocking call to build a CompanyProfile from yfinance ticker.info.

        Args:
            symbol: Ticker symbol (already upper-cased).

        Returns:
            CompanyProfile model.

        Raises:
            NotFoundError: Symbol not found or empty info returned.
        """
        ticker = yf.Ticker(symbol)
        info: Dict[str, Any] = ticker.info or {}

        if not info or info.get("trailingPegRatio") is None and not info.get("longName"):
            # A completely empty or minimal dict usually means invalid symbol
            if not info.get("symbol") and not info.get("longName"):
                raise NotFoundError(
                    self.SERVICE_NAME,
                    symbol,
                    message=f"No company information found for '{symbol}'.",
                )

        return CompanyProfile(
            symbol=info.get("symbol", symbol),
            company_name=info.get("longName") or info.get("shortName", symbol),
            exchange=info.get("exchange", ""),
            sector=info.get("sector"),
            industry=info.get("industry"),
            description=info.get("longBusinessSummary"),
            ceo=info.get("companyOfficers", [{}])[0].get("name") if info.get("companyOfficers") else None,
            website=info.get("website"),
            country=info.get("country"),
            employees=info.get("fullTimeEmployees"),
            currency=info.get("currency", "USD"),
            market_cap=info.get("marketCap"),
            beta=info.get("beta"),
            price=info.get("regularMarketPrice") or info.get("currentPrice"),
            avg_volume=info.get("averageVolume"),
            ipo_date=None,  # Not reliably available via yfinance
            image=None,
            is_etf=info.get("quoteType", "").upper() == "ETF",
            is_actively_trading=not info.get("isDelisted", False),
            source=self.SERVICE_NAME,
        )

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _map_interval(interval: str) -> str:
        """
        Map our canonical interval name to a yfinance interval string.

        Args:
            interval: Our API interval (e.g. "1d", "1w", "1M").

        Returns:
            yfinance interval string.

        Raises:
            ServiceError: Unrecognised interval.
        """
        mapped = _INTERVAL_MAP.get(interval)
        if mapped is None:
            raise ServiceError(
                message=(
                    f"Unsupported interval '{interval}'. "
                    f"Supported values: {sorted(_INTERVAL_MAP.keys())}"
                ),
                service=YFinanceService.SERVICE_NAME,
            )
        return mapped

    @staticmethod
    def _resolve_period(period: Optional[str], start: Optional[str]) -> str:
        """
        Return the effective period string to pass to yfinance.

        When *start* is given the caller controls the date range, so period is
        irrelevant. When neither *period* nor *start* is provided we default to
        ``_DEFAULT_PERIOD``.

        Args:
            period: Caller-supplied period string (may be None).
            start:  Caller-supplied start date (may be None).

        Returns:
            Resolved period string.
        """
        if start:
            return _DEFAULT_PERIOD  # Won't be used when start is present
        if period and period in _VALID_PERIODS:
            return period
        if period:
            logger.warning(
                "invalid_period_defaulted",
                service=YFinanceService.SERVICE_NAME,
                requested=period,
                default=_DEFAULT_PERIOD,
            )
        return _DEFAULT_PERIOD

    @staticmethod
    def _detect_asset_type(ticker: yf.Ticker) -> AssetType:
        """
        Detect the asset type from yfinance fast_info / info.

        Args:
            ticker: yfinance Ticker instance.

        Returns:
            Appropriate AssetType enum value.
        """
        try:
            qt = ticker.fast_info.get("quoteType", "").upper()
        except Exception:
            qt = ""

        if qt == "ETF":
            return AssetType.ETF
        if qt == "CRYPTOCURRENCY":
            return AssetType.CRYPTO
        if qt in ("INDEX", "MUTUALFUND"):
            return AssetType.INDEX
        return AssetType.STOCK

    @staticmethod
    def _safe_float(obj: Any, key: str) -> Optional[float]:
        """
        Safely extract a float value from a dict-like object.

        Args:
            obj: Dict or dict-like (e.g. FastInfo).
            key: Key to look up.

        Returns:
            Float value or None if missing / non-numeric.
        """
        try:
            val = obj[key] if hasattr(obj, "__getitem__") else getattr(obj, key, None)
            return float(val) if val is not None else None
        except (KeyError, AttributeError, TypeError, ValueError):
            return None
