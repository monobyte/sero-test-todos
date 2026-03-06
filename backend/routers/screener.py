"""
Screener router — filter stocks and cryptocurrencies by price, volume,
change %, market-cap, and technical indicators.

Endpoints
---------
GET  /api/screener                 – Filter by basic market criteria
POST /api/screener/technical       – Filter by computed technical indicators
                                     (RSI, SMA crossover, EMA, MACD, Bollinger Bands)

Data Sources
-----------
- Crypto screening  → CoinGecko (top 250 by market cap via /coins/markets)
- Stock screening   → yfinance quotes for a configurable universe (defaults to
                      the DEFAULT_STOCK_UNIVERSE list of ~120 liquid US equities)
- Technical data    → yfinance historical OHLCV (3-month lookback by default)

Rate Limiting / Caching
-----------------------
All service calls go through the shared cache and rate-limiter.  Repeat
screener calls within the quote TTL (60 s) hit the cache with zero upstream
API calls.

Indicator Implementations
--------------------------
All technical indicators are computed in pure NumPy from recent OHLCV data:

  RSI  (Relative Strength Index)     — Wilder smoothing, period configurable
  SMA  (Simple Moving Average)       — Arithmetic mean crossover
  EMA  (Exponential Moving Average)  — Compare EMA to current price
  MACD (Moving Avg Convergence/Div.) — 12/26/9 with configurable periods
  BB   (Bollinger Bands)             — 20-period ±2σ
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

import numpy as np
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from models.market import AssetType, Quote
from services.coingecko_service import CoinGeckoService
from services.finnhub_service import FinnhubService
from services.yfinance_service import YFinanceService
from services.base import NotFoundError, RateLimitError, ServiceError
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/screener", tags=["Screener"])

# ---------------------------------------------------------------------------
# Default stock universe (~120 liquid US equities across sectors)
# Used when no explicit symbols list is provided for stock screens.
# ---------------------------------------------------------------------------
DEFAULT_STOCK_UNIVERSE: List[str] = [
    # Mega-cap tech
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    # Semiconductors
    "AVGO", "AMD", "INTC", "QCOM", "TXN", "MU", "AMAT",
    # Software / cloud
    "ADBE", "CRM", "ORCL", "NOW", "SNOW", "PLTR", "DDOG",
    # Consumer
    "WMT", "COST", "HD", "NKE", "SBUX", "MCD", "TGT",
    # Finance
    "JPM", "BAC", "GS", "MS", "V", "MA", "PYPL", "AXP",
    # Healthcare / pharma
    "JNJ", "UNH", "PFE", "ABBV", "MRK", "LLY", "AMGN", "GILD",
    "TMO", "ABT", "DHR", "MDT",
    # Industrials / defence
    "CAT", "DE", "HON", "GE", "MMM", "BA", "RTX", "LMT",
    # Energy
    "XOM", "CVX", "COP", "SLB",
    # Utilities / telecom
    "NEE", "DUK", "T", "VZ",
    # Consumer staples
    "PG", "KO", "PEP", "PM", "MO",
    # Media / streaming
    "DIS", "NFLX", "CMCSA", "CHTR",
    # Growth / disruptive
    "UBER", "ABNB", "COIN", "SQ", "SOFI",
    # EV / mobility
    "RIVN", "NIO", "LCID",
    # ETFs (broad market reference)
    "SPY", "QQQ", "IWM",
]

# Maximum number of symbols that can be screened per request
MAX_SYMBOLS_PER_REQUEST = 200

# Concurrency limit when fetching quotes in parallel
_QUOTE_CONCURRENCY = 10

# Minimum number of candles required for technical indicator calculation
_MIN_CANDLES_FOR_INDICATORS = 30


# ---------------------------------------------------------------------------
# Pydantic models — request / response
# ---------------------------------------------------------------------------


class ScreenerResult(BaseModel):
    """A single result row from the basic screener."""

    symbol: str = Field(..., description="Ticker symbol")
    asset_type: AssetType = Field(..., description="Asset type (stock or crypto)")
    price: float = Field(..., description="Current price")
    change_percent: float = Field(..., description="24-hour percentage change")
    volume: Optional[float] = Field(None, description="24-hour trading volume")
    market_cap: Optional[float] = Field(None, description="Market capitalisation")
    source: str = Field(..., description="Data source")

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "AAPL",
                "asset_type": "stock",
                "price": 178.50,
                "change_percent": 1.33,
                "volume": 52347890,
                "market_cap": 2800000000000,
                "source": "finnhub",
            }
        }


class ScreenerResponse(BaseModel):
    """Response from the basic screener endpoint."""

    results: List[ScreenerResult] = Field(..., description="Matching assets")
    count: int = Field(..., description="Number of results returned")
    criteria: Dict[str, Any] = Field(..., description="Applied filter criteria")
    total_screened: int = Field(..., description="Total assets examined before filtering")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


class TechnicalIndicatorSpec(BaseModel):
    """Specification for a single technical indicator filter."""

    type: Literal["rsi", "sma_cross", "ema", "macd", "bb"] = Field(
        ..., description="Indicator type"
    )
    # Common parameters
    period: Optional[int] = Field(None, ge=2, le=500, description="Main period")
    min_value: Optional[float] = Field(None, description="Minimum indicator value to pass")
    max_value: Optional[float] = Field(None, description="Maximum indicator value to pass")

    # SMA / EMA crossover parameters
    short_period: Optional[int] = Field(None, ge=2, description="Short MA period (sma_cross)")
    long_period: Optional[int] = Field(None, ge=2, description="Long MA period (sma_cross)")
    direction: Optional[Literal["bullish", "bearish"]] = Field(
        None, description="Cross direction: bullish (short > long) or bearish"
    )

    @field_validator("long_period")
    @classmethod
    def long_must_exceed_short(cls, v: Optional[int], info: Any) -> Optional[int]:
        short = info.data.get("short_period")
        if v is not None and short is not None and v <= short:
            raise ValueError("long_period must be greater than short_period")
        return v


class TechnicalScreenerRequest(BaseModel):
    """Request body for the technical screener."""

    asset_type: AssetType = Field(
        default=AssetType.STOCK, description="Asset universe to screen"
    )
    symbols: Optional[List[str]] = Field(
        None,
        max_length=MAX_SYMBOLS_PER_REQUEST,
        description=(
            "Symbols to screen. If omitted, defaults to DEFAULT_STOCK_UNIVERSE "
            "(stocks) or top-100 CoinGecko coins (crypto)."
        ),
    )
    indicators: List[TechnicalIndicatorSpec] = Field(
        ...,
        min_length=1,
        description="One or more indicator filters — all must pass (AND logic)",
    )
    limit: int = Field(default=50, ge=1, le=200, description="Maximum results to return")

    class Config:
        json_schema_extra = {
            "example": {
                "asset_type": "stock",
                "symbols": ["AAPL", "MSFT", "GOOGL", "NVDA"],
                "indicators": [
                    {"type": "rsi", "period": 14, "max_value": 40},
                    {"type": "sma_cross", "short_period": 50, "long_period": 200, "direction": "bullish"},
                ],
                "limit": 20,
            }
        }


class TechnicalScreenerResult(BaseModel):
    """A single result row from the technical screener."""

    symbol: str
    price: float
    change_percent: float
    indicators: Dict[str, Any] = Field(..., description="Computed indicator values")
    signal: Optional[str] = Field(None, description="Overall signal (buy / sell / neutral)")
    source: str


class TechnicalScreenerResponse(BaseModel):
    """Response from the technical screener endpoint."""

    results: List[TechnicalScreenerResult]
    count: int
    total_screened: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


# ---------------------------------------------------------------------------
# Technical indicator computation (pure NumPy)
# ---------------------------------------------------------------------------


def _compute_rsi(closes: np.ndarray, period: int = 14) -> float:
    """
    Compute RSI using Wilder's smoothing method.

    Args:
        closes: 1-D array of closing prices (oldest → newest).
        period: Look-back window (default 14).

    Returns:
        RSI value in [0, 100].
    """
    if len(closes) < period + 1:
        return float("nan")

    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    # Seed with simple averages over the first `period` values
    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()

    # Wilder's smoothing over remaining values
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))


def _compute_sma(closes: np.ndarray, period: int) -> float:
    """Return the most-recent simple moving average."""
    if len(closes) < period:
        return float("nan")
    return float(closes[-period:].mean())


def _compute_ema(closes: np.ndarray, period: int) -> float:
    """Return the most-recent EMA value using a standard multiplier."""
    if len(closes) < period:
        return float("nan")
    k = 2.0 / (period + 1)
    ema = closes[:period].mean()
    for price in closes[period:]:
        ema = price * k + ema * (1 - k)
    return float(ema)


def _compute_macd(
    closes: np.ndarray,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Dict[str, float]:
    """
    Compute MACD line, signal line, and histogram.

    Returns dict with keys: ``macd``, ``signal``, ``histogram``.
    All values may be NaN if insufficient data.
    """
    nan_result = {"macd": float("nan"), "signal": float("nan"), "histogram": float("nan")}
    if len(closes) < slow + signal:
        return nan_result

    # Build full EMA series
    def ema_series(arr: np.ndarray, span: int) -> np.ndarray:
        k = 2.0 / (span + 1)
        out = np.empty(len(arr))
        out[0] = arr[0]
        for i in range(1, len(arr)):
            out[i] = arr[i] * k + out[i - 1] * (1 - k)
        return out

    ema_fast = ema_series(closes, fast)
    ema_slow = ema_series(closes, slow)
    macd_line = ema_fast - ema_slow
    sig_line = ema_series(macd_line, signal)
    hist = macd_line[-1] - sig_line[-1]

    return {
        "macd": float(macd_line[-1]),
        "signal": float(sig_line[-1]),
        "histogram": float(hist),
    }


def _compute_bollinger(
    closes: np.ndarray, period: int = 20, num_std: float = 2.0
) -> Dict[str, float]:
    """
    Compute Bollinger Bands.

    Returns dict with keys: ``upper``, ``middle``, ``lower``, ``bandwidth``,
    ``percent_b``.
    """
    nan_result = {
        "upper": float("nan"),
        "middle": float("nan"),
        "lower": float("nan"),
        "bandwidth": float("nan"),
        "percent_b": float("nan"),
    }
    if len(closes) < period:
        return nan_result

    window = closes[-period:]
    middle = float(window.mean())
    std = float(window.std(ddof=0))
    upper = middle + num_std * std
    lower = middle - num_std * std
    bandwidth = (upper - lower) / middle if middle != 0 else float("nan")
    last = float(closes[-1])
    percent_b = (last - lower) / (upper - lower) if (upper - lower) != 0 else float("nan")

    return {
        "upper": upper,
        "middle": middle,
        "lower": lower,
        "bandwidth": bandwidth,
        "percent_b": percent_b,
    }


def _compute_indicators(
    closes: np.ndarray,
    specs: List[TechnicalIndicatorSpec],
) -> Dict[str, Any]:
    """
    Compute all requested indicator values for a symbol's close-price array.

    Args:
        closes: Sorted (oldest first) NumPy array of closing prices.
        specs:  Indicator specifications from the request body.

    Returns:
        Dictionary of computed values (may include NaN).
    """
    values: Dict[str, Any] = {}
    for spec in specs:
        itype = spec.type

        if itype == "rsi":
            period = spec.period or 14
            values[f"rsi_{period}"] = _compute_rsi(closes, period)

        elif itype == "sma_cross":
            short = spec.short_period or 50
            long_ = spec.long_period or 200
            values[f"sma_{short}"] = _compute_sma(closes, short)
            values[f"sma_{long_}"] = _compute_sma(closes, long_)
            s_val = values[f"sma_{short}"]
            l_val = values[f"sma_{long_}"]
            if not (np.isnan(s_val) or np.isnan(l_val)):
                values["sma_cross_signal"] = "bullish" if s_val > l_val else "bearish"
            else:
                values["sma_cross_signal"] = None

        elif itype == "ema":
            period = spec.period or 20
            values[f"ema_{period}"] = _compute_ema(closes, period)

        elif itype == "macd":
            macd_vals = _compute_macd(closes)
            values.update(macd_vals)

        elif itype == "bb":
            period = spec.period or 20
            bb_vals = _compute_bollinger(closes, period)
            values.update(bb_vals)

    return values


def _passes_indicator(
    spec: TechnicalIndicatorSpec,
    computed: Dict[str, Any],
    current_price: float,
) -> bool:
    """
    Test whether the computed indicator values satisfy one indicator spec.

    Args:
        spec:          The indicator specification from the request.
        computed:      Computed indicator values for this symbol.
        current_price: Latest closing price.

    Returns:
        True if the symbol passes this filter, False otherwise.
    """
    itype = spec.type

    if itype == "rsi":
        period = spec.period or 14
        val = computed.get(f"rsi_{period}", float("nan"))
        if np.isnan(val):
            return False
        if spec.min_value is not None and val < spec.min_value:
            return False
        if spec.max_value is not None and val > spec.max_value:
            return False

    elif itype == "sma_cross":
        cross = computed.get("sma_cross_signal")
        if cross is None:
            return False
        if spec.direction is not None and cross != spec.direction:
            return False

    elif itype == "ema":
        period = spec.period or 20
        val = computed.get(f"ema_{period}", float("nan"))
        if np.isnan(val):
            return False
        # min_value / max_value are compared against (price - EMA)
        diff = current_price - val
        if spec.min_value is not None and diff < spec.min_value:
            return False
        if spec.max_value is not None and diff > spec.max_value:
            return False

    elif itype == "macd":
        macd_val = computed.get("macd", float("nan"))
        hist_val = computed.get("histogram", float("nan"))
        if np.isnan(macd_val):
            return False
        # min_value / max_value apply to the histogram
        if spec.min_value is not None and hist_val < spec.min_value:
            return False
        if spec.max_value is not None and hist_val > spec.max_value:
            return False

    elif itype == "bb":
        pct_b = computed.get("percent_b", float("nan"))
        if np.isnan(pct_b):
            return False
        if spec.min_value is not None and pct_b < spec.min_value:
            return False
        if spec.max_value is not None and pct_b > spec.max_value:
            return False

    return True


def _derive_signal(specs: List[TechnicalIndicatorSpec], computed: Dict[str, Any]) -> Optional[str]:
    """
    Derive a simple overall signal from the computed indicator values.

    Heuristic: count bullish vs bearish signals across indicators.
    - bullish: RSI < 40, MACD histogram > 0, SMA cross bullish, BB % < 0.2
    - bearish: RSI > 60, MACD histogram < 0, SMA cross bearish, BB % > 0.8
    """
    bullish_count = 0
    bearish_count = 0

    for spec in specs:
        itype = spec.type
        if itype == "rsi":
            period = spec.period or 14
            rsi = computed.get(f"rsi_{period}", float("nan"))
            if not np.isnan(rsi):
                if rsi < 40:
                    bullish_count += 1
                elif rsi > 60:
                    bearish_count += 1
        elif itype == "sma_cross":
            cross = computed.get("sma_cross_signal")
            if cross == "bullish":
                bullish_count += 1
            elif cross == "bearish":
                bearish_count += 1
        elif itype == "macd":
            hist = computed.get("histogram", float("nan"))
            if not np.isnan(hist):
                if hist > 0:
                    bullish_count += 1
                elif hist < 0:
                    bearish_count += 1
        elif itype == "bb":
            pct_b = computed.get("percent_b", float("nan"))
            if not np.isnan(pct_b):
                if pct_b < 0.2:
                    bullish_count += 1
                elif pct_b > 0.8:
                    bearish_count += 1

    if bullish_count > bearish_count:
        return "buy"
    elif bearish_count > bullish_count:
        return "sell"
    else:
        return "neutral"


# ---------------------------------------------------------------------------
# Quote fetching helpers
# ---------------------------------------------------------------------------


async def _fetch_stock_quote_safe(
    service: YFinanceService,
    symbol: str,
) -> Optional[Quote]:
    """Fetch a stock quote, returning None on any error (never raises)."""
    try:
        return await service.get_quote(symbol)
    except (NotFoundError, RateLimitError, ServiceError) as exc:
        logger.debug("quote_fetch_failed", symbol=symbol, error=str(exc))
        return None
    except Exception as exc:
        logger.warning("unexpected_quote_error", symbol=symbol, error=str(exc))
        return None


async def _fetch_stock_quotes_batch(
    symbols: List[str],
    concurrency: int = _QUOTE_CONCURRENCY,
) -> List[Quote]:
    """
    Fetch stock quotes for many symbols concurrently using a semaphore.

    Args:
        symbols:     List of ticker symbols.
        concurrency: Maximum simultaneous requests.

    Returns:
        List of successfully fetched Quote objects (failures are silently dropped).
    """
    sem = asyncio.Semaphore(concurrency)
    yf = YFinanceService()

    async def _guarded(sym: str) -> Optional[Quote]:
        async with sem:
            return await _fetch_stock_quote_safe(yf, sym)

    tasks = [_guarded(sym) for sym in symbols]
    results = await asyncio.gather(*tasks)
    return [q for q in results if q is not None]


def _apply_quote_filters(
    quotes: List[Quote],
    min_price: Optional[float],
    max_price: Optional[float],
    min_volume: Optional[float],
    max_volume: Optional[float],
    min_change_percent: Optional[float],
    max_change_percent: Optional[float],
    min_market_cap: Optional[float],
    max_market_cap: Optional[float],
) -> List[Quote]:
    """Apply numerical filter criteria to a list of quotes."""
    out = []
    for q in quotes:
        if min_price is not None and q.price < min_price:
            continue
        if max_price is not None and q.price > max_price:
            continue
        if min_volume is not None and (q.volume is None or q.volume < min_volume):
            continue
        if max_volume is not None and (q.volume is None or q.volume > max_volume):
            continue
        if min_change_percent is not None and q.change_percent < min_change_percent:
            continue
        if max_change_percent is not None and q.change_percent > max_change_percent:
            continue
        if min_market_cap is not None and (q.market_cap is None or q.market_cap < min_market_cap):
            continue
        if max_market_cap is not None and (q.market_cap is None or q.market_cap > max_market_cap):
            continue
        out.append(q)
    return out


# ---------------------------------------------------------------------------
# GET /api/screener
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=ScreenerResponse,
    status_code=status.HTTP_200_OK,
    summary="Screen assets by market criteria",
    description=(
        "Filter stocks or cryptocurrencies by price, volume, percentage change, "
        "and market capitalisation. Crypto data comes from CoinGecko's top-250 list; "
        "stock data from yfinance (default universe) or a custom symbol list."
    ),
)
async def screen_assets(
    asset_type: AssetType = Query(..., description="Asset universe: 'stock' or 'crypto'"),
    symbols: Optional[str] = Query(
        None,
        description=(
            "Comma-separated list of symbols to screen "
            f"(max {MAX_SYMBOLS_PER_REQUEST}). "
            "Omit to use the default universe."
        ),
    ),
    min_price: Optional[float] = Query(None, ge=0, description="Minimum price"),
    max_price: Optional[float] = Query(None, ge=0, description="Maximum price"),
    min_volume: Optional[float] = Query(None, ge=0, description="Minimum 24h volume"),
    max_volume: Optional[float] = Query(None, ge=0, description="Maximum 24h volume"),
    min_change_percent: Optional[float] = Query(
        None, description="Minimum 24h percentage change"
    ),
    max_change_percent: Optional[float] = Query(
        None, description="Maximum 24h percentage change"
    ),
    min_market_cap: Optional[float] = Query(None, ge=0, description="Minimum market cap"),
    max_market_cap: Optional[float] = Query(None, ge=0, description="Maximum market cap"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of results"),
) -> ScreenerResponse:
    """
    Screen assets by basic market criteria.

    For **crypto**, CoinGecko's top-250 list is fetched and filtered in-memory.
    For **stocks**, yfinance quotes are fetched concurrently for the provided
    (or default) symbol universe and then filtered.
    """
    logger.info(
        "screener_request",
        asset_type=asset_type,
        min_price=min_price,
        max_price=max_price,
        min_change_percent=min_change_percent,
        limit=limit,
    )

    # Parse custom symbol list
    symbol_list: Optional[List[str]] = None
    if symbols:
        symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if len(symbol_list) > MAX_SYMBOLS_PER_REQUEST:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Too many symbols. Maximum is {MAX_SYMBOLS_PER_REQUEST}.",
            )

    # Collect raw quotes
    quotes: List[Quote] = []

    if asset_type == AssetType.CRYPTO:
        quotes = await _screen_crypto(symbol_list)
    else:
        quotes = await _screen_stocks(symbol_list)

    total_screened = len(quotes)

    # Apply filters
    filtered = _apply_quote_filters(
        quotes,
        min_price=min_price,
        max_price=max_price,
        min_volume=min_volume,
        max_volume=max_volume,
        min_change_percent=min_change_percent,
        max_change_percent=max_change_percent,
        min_market_cap=min_market_cap,
        max_market_cap=max_market_cap,
    )

    # Sort by absolute change (biggest movers first)
    filtered.sort(key=lambda q: abs(q.change_percent), reverse=True)
    filtered = filtered[:limit]

    results = [
        ScreenerResult(
            symbol=q.symbol,
            asset_type=q.asset_type,
            price=q.price,
            change_percent=q.change_percent,
            volume=q.volume,
            market_cap=q.market_cap,
            source=q.source,
        )
        for q in filtered
    ]

    criteria: Dict[str, Any] = {"asset_type": asset_type.value}
    if min_price is not None:
        criteria["min_price"] = min_price
    if max_price is not None:
        criteria["max_price"] = max_price
    if min_volume is not None:
        criteria["min_volume"] = min_volume
    if max_volume is not None:
        criteria["max_volume"] = max_volume
    if min_change_percent is not None:
        criteria["min_change_percent"] = min_change_percent
    if max_change_percent is not None:
        criteria["max_change_percent"] = max_change_percent
    if min_market_cap is not None:
        criteria["min_market_cap"] = min_market_cap
    if max_market_cap is not None:
        criteria["max_market_cap"] = max_market_cap
    if symbol_list:
        criteria["symbols"] = symbol_list

    logger.info(
        "screener_complete",
        total_screened=total_screened,
        results_returned=len(results),
    )

    return ScreenerResponse(
        results=results,
        count=len(results),
        criteria=criteria,
        total_screened=total_screened,
    )


async def _screen_crypto(symbol_list: Optional[List[str]]) -> List[Quote]:
    """
    Fetch crypto quotes from CoinGecko.

    If *symbol_list* is provided, fetches only those coins (via batch quote).
    Otherwise, fetches the top-250 by market cap.
    """
    cg = CoinGeckoService()
    try:
        if symbol_list:
            batch = await cg.get_crypto_quotes_batch(symbol_list)
            return list(batch.values())
        else:
            # top_coins returns dicts; we need Quote objects
            top = await cg.get_top_coins(limit=250)
            quotes: List[Quote] = []
            for item in top:
                try:
                    from models.market import OHLCV  # noqa: F401 (unused but available)
                    from datetime import datetime as _dt
                    sym = item.get("symbol", "").upper()
                    if not sym:
                        continue
                    quotes.append(
                        Quote(
                            symbol=sym,
                            asset_type=AssetType.CRYPTO,
                            price=float(item.get("current_price") or 0),
                            change=float(item.get("price_change_24h") or 0),
                            change_percent=float(
                                item.get("price_change_percentage_24h") or 0
                            ),
                            volume=float(item["total_volume"])
                            if item.get("total_volume") is not None
                            else None,
                            market_cap=float(item["market_cap"])
                            if item.get("market_cap") is not None
                            else None,
                            high_24h=float(item["high_24h"])
                            if item.get("high_24h") is not None
                            else None,
                            low_24h=float(item["low_24h"])
                            if item.get("low_24h") is not None
                            else None,
                            timestamp=datetime.now(tz=timezone.utc),
                            source="coingecko",
                        )
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    logger.debug("crypto_parse_error", item=item, error=str(exc))
            return quotes
    except (RateLimitError, ServiceError) as exc:
        logger.error("crypto_screener_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"CoinGecko data unavailable: {exc}",
        )


async def _screen_stocks(symbol_list: Optional[List[str]]) -> List[Quote]:
    """
    Fetch stock quotes using yfinance.

    Uses *symbol_list* when provided, otherwise falls back to DEFAULT_STOCK_UNIVERSE.
    """
    universe = symbol_list if symbol_list else DEFAULT_STOCK_UNIVERSE
    try:
        return await _fetch_stock_quotes_batch(universe)
    except Exception as exc:
        logger.error("stock_screener_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Stock data unavailable: {exc}",
        )


# ---------------------------------------------------------------------------
# POST /api/screener/technical
# ---------------------------------------------------------------------------


@router.post(
    "/technical",
    response_model=TechnicalScreenerResponse,
    status_code=status.HTTP_200_OK,
    summary="Screen assets by technical indicators",
    description=(
        "Compute RSI, SMA crossover, EMA, MACD, and Bollinger Bands from recent "
        "OHLCV data and return only the assets that satisfy all specified indicator "
        "filters (AND logic). Historical data is sourced from yfinance."
    ),
)
async def technical_screener(body: TechnicalScreenerRequest) -> TechnicalScreenerResponse:
    """
    Screen stocks or crypto using technical indicator criteria.

    Historical data (3-month daily candles) is fetched from yfinance for each
    candidate symbol.  All indicator filters must be satisfied simultaneously
    (AND logic) for a symbol to appear in the results.

    Supported indicator types:
    - **rsi**: Relative Strength Index. ``min_value``/``max_value`` filter on the RSI value.
    - **sma_cross**: SMA crossover. ``direction`` can be ``"bullish"`` (short > long) or
      ``"bearish"``.
    - **ema**: EMA distance. ``min_value``/``max_value`` filter on (price − EMA).
    - **macd**: MACD histogram. ``min_value``/``max_value`` filter on the histogram value.
    - **bb**: Bollinger Bands %B. ``min_value``/``max_value`` filter on %B (0 = lower band,
      1 = upper band).
    """
    logger.info(
        "technical_screener_request",
        asset_type=body.asset_type,
        indicators=[s.type for s in body.indicators],
        symbol_count=len(body.symbols) if body.symbols else "default",
    )

    # Resolve symbol universe
    if body.symbols:
        universe = [s.upper() for s in body.symbols]
    elif body.asset_type == AssetType.CRYPTO:
        # Use top-100 CoinGecko symbols from the static lookup table
        from services.coingecko_service import SYMBOL_TO_COINGECKO_ID

        universe = list(SYMBOL_TO_COINGECKO_ID.keys())[:100]
    else:
        universe = DEFAULT_STOCK_UNIVERSE

    # Determine the minimum number of candles needed across all indicators
    min_candles = _MIN_CANDLES_FOR_INDICATORS
    for spec in body.indicators:
        for p in (spec.period, spec.long_period):
            if p is not None and p > min_candles:
                min_candles = p

    # How many days of 1-day candles we need (with buffer)
    needed_days = min_candles + 50  # generous buffer for weekends / holidays
    period_str = "6mo" if needed_days <= 126 else "1y"

    # Fetch historical data for all symbols concurrently
    yf = YFinanceService()
    sem = asyncio.Semaphore(_QUOTE_CONCURRENCY)
    results: List[TechnicalScreenerResult] = []
    total_screened = 0

    async def _process_symbol(sym: str) -> Optional[TechnicalScreenerResult]:
        nonlocal total_screened
        async with sem:
            try:
                hist = await yf.get_historical(sym, interval="1d", period=period_str)
            except (NotFoundError, ServiceError):
                return None
            except Exception as exc:
                logger.debug("hist_fetch_error", symbol=sym, error=str(exc))
                return None

        if not hist.candles:
            return None

        closes = np.array([c.close for c in hist.candles], dtype=float)
        if len(closes) < _MIN_CANDLES_FOR_INDICATORS:
            return None

        total_screened += 1
        current_price = float(closes[-1])

        # Compute all indicators
        computed = _compute_indicators(closes, body.indicators)

        # Apply all filters (AND logic)
        for spec in body.indicators:
            if not _passes_indicator(spec, computed, current_price):
                return None

        # Calculate change_percent from last two closes
        change_percent = 0.0
        if len(closes) >= 2 and closes[-2] != 0:
            change_percent = float((closes[-1] - closes[-2]) / closes[-2] * 100)

        signal = _derive_signal(body.indicators, computed)

        # Sanitise NaN values so they serialise as null
        sanitised: Dict[str, Any] = {}
        for k, v in computed.items():
            if isinstance(v, float) and np.isnan(v):
                sanitised[k] = None
            else:
                sanitised[k] = v

        return TechnicalScreenerResult(
            symbol=sym,
            price=current_price,
            change_percent=round(change_percent, 4),
            indicators=sanitised,
            signal=signal,
            source="yfinance",
        )

    tasks = [_process_symbol(sym) for sym in universe]
    raw_results = await asyncio.gather(*tasks)

    for r in raw_results:
        if r is not None:
            results.append(r)

    # Sort by absolute change, take top-N
    results.sort(key=lambda r: abs(r.change_percent), reverse=True)
    results = results[: body.limit]

    logger.info(
        "technical_screener_complete",
        total_screened=total_screened,
        results_returned=len(results),
    )

    return TechnicalScreenerResponse(
        results=results,
        count=len(results),
        total_screened=total_screened,
    )
