"""
Historical data router — OHLCV candle data for stocks and cryptocurrencies.

Endpoint:
    GET /api/historical/{symbol}

Fallback chains (no explicit source):
    Stocks:  Finnhub → yfinance
    Crypto:  CoinGecko → yfinance

Parameters:
    interval  — Candle resolution (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1M)
    from      — Start date (YYYY-MM-DD or ISO 8601), maps to query alias
    to        — End date  (YYYY-MM-DD or ISO 8601), maps to query alias
    limit     — Max candles returned (default 100, max 5000); trims newest-first
    source    — Pin a specific provider (finnhub, coingecko, yfinance)
"""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from models.market import OHLCV, AssetType, HistoricalData
from services import (
    AuthenticationError,
    CoinGeckoService,
    NotFoundError,
    RateLimitError,
    ServiceError,
    SYMBOL_TO_COINGECKO_ID,
    YFinanceService,
)
from services.finnhub_service import FinnhubService
from utils import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/historical", tags=["Historical"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_SOURCES = frozenset({"finnhub", "coingecko", "yfinance"})

VALID_INTERVALS = frozenset({"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"})

# Approximate yfinance period string that yields enough candles for each interval.
# These are generous — the limit parameter trims the result.
_INTERVAL_YFINANCE_PERIOD = {
    "1m": "7d",
    "5m": "60d",
    "15m": "60d",
    "30m": "60d",
    "1h": "2y",
    "4h": "2y",
    "1d": "5y",
    "1w": "10y",
    "1M": "max",
}

# Default days to request from CoinGecko when no date range is supplied.
# Chosen to match the auto-granularity that CoinGecko applies:
#   ≤ 1 day → ~5-min data
#   2–90 days → hourly
#   > 90 days → daily
_INTERVAL_CG_DAYS = {
    "1m": 1,
    "5m": 1,
    "15m": 2,
    "30m": 3,
    "1h": 30,
    "4h": 90,
    "1d": 365,
    "1w": 730,
    "1M": 1825,
}

# ---------------------------------------------------------------------------
# Singleton service instances
# ---------------------------------------------------------------------------

_finnhub_svc: Optional[FinnhubService] = None
_coingecko_svc: Optional[CoinGeckoService] = None
_yfinance_svc: Optional[YFinanceService] = None


def _get_finnhub() -> FinnhubService:
    global _finnhub_svc
    if _finnhub_svc is None:
        _finnhub_svc = FinnhubService()
    return _finnhub_svc


def _get_coingecko() -> CoinGeckoService:
    global _coingecko_svc
    if _coingecko_svc is None:
        _coingecko_svc = CoinGeckoService()
    return _coingecko_svc


def _get_yfinance() -> YFinanceService:
    global _yfinance_svc
    if _yfinance_svc is None:
        _yfinance_svc = YFinanceService()
    return _yfinance_svc


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class HistoricalResponse(BaseModel):
    """Historical data response enriched with a candle count."""

    symbol: str
    asset_type: AssetType
    interval: str
    candles: List[OHLCV]
    count: int
    source: str

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "AAPL",
                "asset_type": "stock",
                "interval": "1d",
                "candles": [
                    {
                        "timestamp": "2026-03-01T00:00:00Z",
                        "open": 148.50,
                        "high": 151.00,
                        "low": 147.80,
                        "close": 150.25,
                        "volume": 45000000,
                    }
                ],
                "count": 1,
                "source": "finnhub",
            }
        }

    @classmethod
    def from_historical_data(cls, data: HistoricalData) -> "HistoricalResponse":
        """Build a HistoricalResponse from a HistoricalData model."""
        return cls(
            symbol=data.symbol,
            asset_type=data.asset_type,
            interval=data.interval,
            candles=data.candles,
            count=len(data.candles),
            source=data.source,
        )


# ---------------------------------------------------------------------------
# Date / range utilities
# ---------------------------------------------------------------------------


def _parse_date(date_str: str) -> datetime:
    """
    Parse a date string in YYYY-MM-DD or ISO 8601 format into a UTC datetime.

    Args:
        date_str: Date/datetime string.

    Returns:
        UTC-aware datetime.

    Raises:
        HTTPException 400: If the string cannot be parsed.
    """
    try:
        # Normalise common formats
        normalised = date_str.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalised)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "ValidationError",
                "message": f"Invalid date format: '{date_str}'. Use YYYY-MM-DD or ISO 8601.",
                "detail": {"examples": ["2026-01-01", "2026-01-01T00:00:00Z"]},
            },
        )


def _to_unix(dt: datetime) -> int:
    """Convert a datetime to a UNIX timestamp (seconds)."""
    return int(dt.timestamp())


def _compute_cg_days(
    interval: str,
    from_date: Optional[str],
    to_date: Optional[str],
) -> int:
    """
    Compute the ``days`` parameter for CoinGecko's ``/market_chart`` endpoint.

    Uses the date range when provided; otherwise falls back to per-interval
    defaults that produce the appropriate granularity.

    Args:
        interval:  Canonical interval string (e.g. "1d").
        from_date: Optional start date string.
        to_date:   Optional end date string.

    Returns:
        Number of days to request from CoinGecko.
    """
    if from_date:
        from_dt = _parse_date(from_date)
        to_dt = _parse_date(to_date) if to_date else datetime.now(tz=timezone.utc)
        days = max(1, (to_dt - from_dt).days + 1)
        return days
    return _INTERVAL_CG_DAYS.get(interval, 30)


def _trim_candles(candles: List[OHLCV], limit: int) -> List[OHLCV]:
    """Return the *limit* most-recent candles (already sorted oldest-first)."""
    if len(candles) > limit:
        return candles[-limit:]
    return candles


# ---------------------------------------------------------------------------
# Error conversion
# ---------------------------------------------------------------------------


def _to_http_exc(
    exc: Exception,
    symbol: str,
    searched: List[str],
) -> HTTPException:
    """Map a ServiceError subclass to the appropriate HTTPException."""
    if isinstance(exc, NotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "NotFound",
                "message": f"Historical data for '{symbol}' not found in any data source",
                "detail": {
                    "symbol": symbol,
                    "searched_sources": searched,
                },
            },
        )
    if isinstance(exc, RateLimitError):
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "RateLimitExceeded",
                "message": "API rate limit exceeded. Please try again later.",
                "detail": {"retry_after": getattr(exc, "retry_after", 60)},
            },
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error": "ServiceUnavailable",
            "message": "All data sources failed. Please try again later.",
            "detail": {
                "symbol": symbol,
                "searched_sources": searched,
            },
        },
    )


# ---------------------------------------------------------------------------
# Fallback orchestration
# ---------------------------------------------------------------------------


async def _fetch_stock_historical(
    symbol: str,
    interval: str,
    from_date: Optional[str],
    to_date: Optional[str],
    limit: int,
    source: Optional[str],
) -> HistoricalResponse:
    """
    Fetch stock historical data via Finnhub → yfinance fallback.

    Args:
        symbol:    Uppercase ticker symbol.
        interval:  Canonical interval (e.g. "1d").
        from_date: Optional start date string.
        to_date:   Optional end date string.
        limit:     Max candles to return (newest subset).
        source:    Optional pinned source name.

    Returns:
        :class:`HistoricalResponse` with trimmed candles.

    Raises:
        HTTPException: On all failure conditions.
    """
    attempted: List[str] = []
    last_error: Exception = ServiceError("No sources attempted", "all")

    # --- Finnhub ---
    if source in (None, "finnhub"):
        attempted.append("finnhub")
        try:
            from_ts = _to_unix(_parse_date(from_date)) if from_date else None
            to_ts = _to_unix(_parse_date(to_date)) if to_date else None

            data = await _get_finnhub().get_candles(
                symbol=symbol,
                resolution=interval,
                from_timestamp=from_ts,
                to_timestamp=to_ts,
            )
            data.candles = _trim_candles(data.candles, limit)
            logger.info(
                "finnhub_historical_success",
                symbol=symbol,
                interval=interval,
                candle_count=len(data.candles),
            )
            return HistoricalResponse.from_historical_data(data)

        except NotFoundError as exc:
            last_error = exc
            if source == "finnhub":
                raise _to_http_exc(exc, symbol, attempted) from exc
            logger.info(
                "finnhub_historical_not_found_trying_fallback",
                symbol=symbol,
                error=str(exc),
            )
        except (RateLimitError, AuthenticationError, ServiceError) as exc:
            last_error = exc
            if source == "finnhub":
                raise _to_http_exc(exc, symbol, attempted) from exc
            logger.warning(
                "finnhub_historical_failed",
                symbol=symbol,
                interval=interval,
                error=str(exc),
            )

    # --- yfinance ---
    if source in (None, "yfinance"):
        attempted.append("yfinance")
        try:
            period = _INTERVAL_YFINANCE_PERIOD.get(interval, "1y") if not from_date else None
            data = await _get_yfinance().get_historical(
                symbol=symbol,
                interval=interval,
                period=period,
                start=from_date,
                end=to_date,
            )
            data.candles = _trim_candles(data.candles, limit)
            logger.info(
                "yfinance_historical_success",
                symbol=symbol,
                interval=interval,
                candle_count=len(data.candles),
            )
            return HistoricalResponse.from_historical_data(data)

        except NotFoundError as exc:
            last_error = exc
            if source == "yfinance":
                raise _to_http_exc(exc, symbol, attempted) from exc
            logger.info(
                "yfinance_historical_not_found",
                symbol=symbol,
                error=str(exc),
            )
        except (RateLimitError, AuthenticationError, ServiceError) as exc:
            last_error = exc
            if source == "yfinance":
                raise _to_http_exc(exc, symbol, attempted) from exc
            logger.warning(
                "yfinance_historical_failed",
                symbol=symbol,
                interval=interval,
                error=str(exc),
            )

    raise _to_http_exc(last_error, symbol, attempted)


async def _fetch_crypto_historical(
    symbol: str,
    interval: str,
    from_date: Optional[str],
    to_date: Optional[str],
    limit: int,
    source: Optional[str],
) -> HistoricalResponse:
    """
    Fetch crypto historical data via CoinGecko → yfinance fallback.

    CoinGecko does not accept arbitrary date ranges via the free API — we
    compute an appropriate ``days`` value from the requested range and rely
    on automatic granularity selection.

    Args:
        symbol:    Crypto ticker or CoinGecko ID.
        interval:  Canonical interval (e.g. "1d").
        from_date: Optional start date string.
        to_date:   Optional end date string.
        limit:     Max candles to return.
        source:    Optional pinned source name.

    Returns:
        :class:`HistoricalResponse` with trimmed candles.

    Raises:
        HTTPException: On all failure conditions.
    """
    attempted: List[str] = []
    last_error: Exception = ServiceError("No sources attempted", "all")

    # --- CoinGecko ---
    if source in (None, "coingecko"):
        attempted.append("coingecko")
        try:
            days = _compute_cg_days(interval, from_date, to_date)
            data = await _get_coingecko().get_historical(symbol=symbol, days=days)
            data.candles = _trim_candles(data.candles, limit)
            logger.info(
                "coingecko_historical_success",
                symbol=symbol,
                days=days,
                candle_count=len(data.candles),
            )
            return HistoricalResponse.from_historical_data(data)

        except NotFoundError as exc:
            last_error = exc
            if source == "coingecko":
                raise _to_http_exc(exc, symbol, attempted) from exc
            logger.info(
                "coingecko_historical_not_found_trying_fallback",
                symbol=symbol,
                error=str(exc),
            )
        except (RateLimitError, AuthenticationError, ServiceError) as exc:
            last_error = exc
            if source == "coingecko":
                raise _to_http_exc(exc, symbol, attempted) from exc
            logger.warning(
                "coingecko_historical_failed",
                symbol=symbol,
                interval=interval,
                error=str(exc),
            )

    # --- yfinance ---
    if source in (None, "yfinance"):
        attempted.append("yfinance")
        try:
            period = _INTERVAL_YFINANCE_PERIOD.get(interval, "1y") if not from_date else None
            data = await _get_yfinance().get_historical(
                symbol=symbol,
                interval=interval,
                period=period,
                start=from_date,
                end=to_date,
            )
            data.candles = _trim_candles(data.candles, limit)
            logger.info(
                "yfinance_crypto_historical_success",
                symbol=symbol,
                interval=interval,
                candle_count=len(data.candles),
            )
            return HistoricalResponse.from_historical_data(data)

        except NotFoundError as exc:
            last_error = exc
            if source == "yfinance":
                raise _to_http_exc(exc, symbol, attempted) from exc
            logger.info(
                "yfinance_crypto_historical_not_found",
                symbol=symbol,
                error=str(exc),
            )
        except (RateLimitError, AuthenticationError, ServiceError) as exc:
            last_error = exc
            if source == "yfinance":
                raise _to_http_exc(exc, symbol, attempted) from exc
            logger.warning(
                "yfinance_crypto_historical_failed",
                symbol=symbol,
                interval=interval,
                error=str(exc),
            )

    raise _to_http_exc(last_error, symbol, attempted)


def _is_crypto_symbol(symbol: str) -> bool:
    """
    Return True if *symbol* is a known cryptocurrency.

    Mirrors the same heuristic used in the quotes router.
    """
    if symbol.upper() in SYMBOL_TO_COINGECKO_ID:
        return True
    if symbol == symbol.lower() and symbol.replace("-", "").isalpha():
        return True
    return False


# ---------------------------------------------------------------------------
# Route handler
# ---------------------------------------------------------------------------


@router.get(
    "/{symbol}",
    response_model=HistoricalResponse,
    summary="Get historical OHLCV data",
    description=(
        "Fetch historical OHLCV (Open, High, Low, Close, Volume) candles for "
        "a stock or cryptocurrency.\n\n"
        "**Stock fallback chain:** Finnhub → yfinance\n\n"
        "**Crypto fallback chain:** CoinGecko → yfinance\n\n"
        "The `limit` parameter returns the *most recent* N candles from the "
        "requested range."
    ),
    responses={
        200: {"description": "Historical data retrieved successfully"},
        400: {"description": "Invalid request parameters"},
        404: {"description": "Symbol not found or no data for range"},
        429: {"description": "Rate limit exceeded"},
        503: {"description": "All data sources failed"},
    },
)
async def get_historical(
    symbol: str,
    interval: str = Query(
        "1d",
        description=(
            "Candle resolution. Supported values: "
            "1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1M"
        ),
    ),
    from_date: Optional[str] = Query(
        None,
        alias="from",
        description="Start date — YYYY-MM-DD or ISO 8601 (e.g. 2026-01-01)",
    ),
    to_date: Optional[str] = Query(
        None,
        alias="to",
        description="End date — YYYY-MM-DD or ISO 8601 (e.g. 2026-03-01)",
    ),
    limit: int = Query(
        100,
        ge=1,
        le=5000,
        description="Maximum number of candles to return (newest subset)",
    ),
    source: Optional[str] = Query(
        None,
        description="Force a specific data source: finnhub, coingecko, yfinance",
    ),
) -> HistoricalResponse:
    """
    Get OHLCV historical candles for a stock or cryptocurrency.

    Asset type is auto-detected using the same heuristic as the quotes router.
    When both `from` and `to` are omitted, a sensible default lookback is
    chosen based on the requested interval.
    """
    # --- Validate interval ---
    if interval not in VALID_INTERVALS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "ValidationError",
                "message": f"Invalid interval '{interval}'",
                "detail": {
                    "field": "interval",
                    "allowed_values": sorted(VALID_INTERVALS),
                },
            },
        )

    # --- Validate source ---
    if source and source not in VALID_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "ValidationError",
                "message": f"Invalid source '{source}'",
                "detail": {"allowed_values": sorted(VALID_SOURCES)},
            },
        )

    # --- Validate date range (parse eagerly to surface format errors early) ---
    if from_date:
        from_dt = _parse_date(from_date)
    else:
        from_dt = None

    if to_date:
        to_dt = _parse_date(to_date)
    else:
        to_dt = None

    if from_dt and to_dt and from_dt >= to_dt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "ValidationError",
                "message": "`from` date must be earlier than `to` date",
            },
        )

    # Normalise symbol
    symbol = symbol.strip()
    normalised = symbol.upper() if not _is_crypto_symbol(symbol) else symbol

    logger.info(
        "historical_request",
        symbol=normalised,
        interval=interval,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        source=source,
    )

    if _is_crypto_symbol(symbol):
        return await _fetch_crypto_historical(
            symbol=normalised,
            interval=interval,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            source=source,
        )

    return await _fetch_stock_historical(
        symbol=normalised,
        interval=interval,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        source=source,
    )
