"""
Quotes router — real-time price data for stocks and cryptocurrencies.

Endpoints:
    GET /api/quotes/batch     — Batch quotes for multiple symbols (concurrent)
    GET /api/quotes/{symbol}  — Single real-time quote with service fallback

Fallback chains (no explicit source):
    Stocks:  Finnhub → yfinance
    Crypto:  CoinGecko → yfinance

Asset type detection uses the SYMBOL_TO_COINGECKO_ID lookup table; symbols
not found there are treated as stock tickers.
"""
import asyncio
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from models import Quote
from models.market import AssetType
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

router = APIRouter(prefix="/api/quotes", tags=["Quotes"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_SOURCES = frozenset({"finnhub", "coingecko", "yfinance"})

# ---------------------------------------------------------------------------
# Singleton service instances (created on first use)
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
# Response models
# ---------------------------------------------------------------------------


class BatchQuoteResponse(BaseModel):
    """Response envelope for batch quote requests."""

    quotes: List[Quote]
    count: int
    failed_symbols: List[str]
    timestamp: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "quotes": [],
                "count": 2,
                "failed_symbols": ["BADINPUT"],
                "timestamp": "2026-03-06T14:00:00Z",
            }
        }


# ---------------------------------------------------------------------------
# Asset-type detection
# ---------------------------------------------------------------------------


def _is_crypto_symbol(symbol: str) -> bool:
    """
    Return True if *symbol* is a known cryptocurrency.

    Detection order:
    1. Check SYMBOL_TO_COINGECKO_ID lookup table (covers 100+ major coins).
    2. Assume CoinGecko ID format when the symbol is entirely lowercase
       (e.g. "bitcoin", "wrapped-bitcoin") — stock tickers are always upper.
    """
    if symbol.upper() in SYMBOL_TO_COINGECKO_ID:
        return True
    # CoinGecko IDs are lowercase with optional hyphens
    if symbol == symbol.lower() and symbol.replace("-", "").isalpha():
        return True
    return False


# ---------------------------------------------------------------------------
# Error conversion
# ---------------------------------------------------------------------------


def _to_http_exc(
    exc: Exception,
    symbol: str,
    searched: List[str],
) -> HTTPException:
    """Map a ServiceError (or subclass) to the appropriate HTTPException."""
    if isinstance(exc, NotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "NotFound",
                "message": f"Symbol '{symbol}' not found in any data source",
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
                "detail": {
                    "retry_after": getattr(exc, "retry_after", 60),
                },
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


async def _fetch_stock_quote(symbol: str, source: Optional[str]) -> Quote:
    """
    Fetch a stock quote using the fallback chain: Finnhub → yfinance.

    When *source* is specified only that service is tried and its error is
    propagated directly without falling back.
    """
    attempted: List[str] = []
    last_error: Exception = ServiceError("No sources attempted", "all")

    # --- Finnhub ---
    if source in (None, "finnhub"):
        attempted.append("finnhub")
        try:
            return await _get_finnhub().get_quote(symbol)
        except NotFoundError as exc:
            last_error = exc
            if source == "finnhub":
                raise _to_http_exc(exc, symbol, attempted) from exc
            logger.info(
                "finnhub_not_found_trying_fallback",
                symbol=symbol,
                error=str(exc),
            )
        except (RateLimitError, AuthenticationError, ServiceError) as exc:
            last_error = exc
            if source == "finnhub":
                raise _to_http_exc(exc, symbol, attempted) from exc
            logger.warning("finnhub_quote_failed", symbol=symbol, error=str(exc))

    # --- yfinance ---
    if source in (None, "yfinance"):
        attempted.append("yfinance")
        try:
            return await _get_yfinance().get_quote(symbol)
        except NotFoundError as exc:
            last_error = exc
            if source == "yfinance":
                raise _to_http_exc(exc, symbol, attempted) from exc
            logger.info("yfinance_not_found", symbol=symbol, error=str(exc))
        except (RateLimitError, AuthenticationError, ServiceError) as exc:
            last_error = exc
            if source == "yfinance":
                raise _to_http_exc(exc, symbol, attempted) from exc
            logger.warning("yfinance_quote_failed", symbol=symbol, error=str(exc))

    raise _to_http_exc(last_error, symbol, attempted)


async def _fetch_crypto_quote(symbol: str, source: Optional[str]) -> Quote:
    """
    Fetch a crypto quote using the fallback chain: CoinGecko → yfinance.

    When *source* is specified only that service is tried.
    """
    attempted: List[str] = []
    last_error: Exception = ServiceError("No sources attempted", "all")

    # --- CoinGecko ---
    if source in (None, "coingecko"):
        attempted.append("coingecko")
        try:
            return await _get_coingecko().get_crypto_quote(symbol)
        except NotFoundError as exc:
            last_error = exc
            if source == "coingecko":
                raise _to_http_exc(exc, symbol, attempted) from exc
            logger.info(
                "coingecko_not_found_trying_fallback",
                symbol=symbol,
                error=str(exc),
            )
        except (RateLimitError, AuthenticationError, ServiceError) as exc:
            last_error = exc
            if source == "coingecko":
                raise _to_http_exc(exc, symbol, attempted) from exc
            logger.warning("coingecko_quote_failed", symbol=symbol, error=str(exc))

    # --- yfinance (fallback — can fetch crypto from Yahoo Finance) ---
    if source in (None, "yfinance"):
        attempted.append("yfinance")
        try:
            return await _get_yfinance().get_quote(symbol)
        except NotFoundError as exc:
            last_error = exc
            if source == "yfinance":
                raise _to_http_exc(exc, symbol, attempted) from exc
            logger.info("yfinance_crypto_not_found", symbol=symbol, error=str(exc))
        except (RateLimitError, AuthenticationError, ServiceError) as exc:
            last_error = exc
            if source == "yfinance":
                raise _to_http_exc(exc, symbol, attempted) from exc
            logger.warning("yfinance_crypto_quote_failed", symbol=symbol, error=str(exc))

    raise _to_http_exc(last_error, symbol, attempted)


async def _fetch_quote(symbol: str, source: Optional[str]) -> Quote:
    """
    Route a quote request to the appropriate service chain.

    Normalises the symbol to uppercase and auto-detects asset type.

    Args:
        symbol: Ticker or CoinGecko ID (case-insensitive).
        source: Optional override — ``finnhub``, ``coingecko``, or ``yfinance``.

    Returns:
        Populated :class:`~models.market.Quote`.

    Raises:
        HTTPException: 400 for invalid source, 404 if not found,
                       429 on rate limit, 503 if all sources fail.
    """
    # Normalise to uppercase first — stock tickers are always uppercase and
    # CoinGecko tickers (BTC, ETH, …) are stored upper-cased in the lookup table.
    # This prevents lowercase stock symbols (e.g. "aapl") from being
    # misidentified as CoinGecko IDs.
    symbol = symbol.strip().upper()

    if source and source not in VALID_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "ValidationError",
                "message": f"Invalid source '{source}'",
                "detail": {"allowed_values": sorted(VALID_SOURCES)},
            },
        )

    if _is_crypto_symbol(symbol):
        logger.info("quote_request_crypto", symbol=symbol, source=source)
        return await _fetch_crypto_quote(symbol, source)

    logger.info("quote_request_stock", symbol=symbol, source=source)
    return await _fetch_stock_quote(symbol, source)


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@router.get(
    "/batch",
    response_model=BatchQuoteResponse,
    summary="Get quotes for multiple symbols",
    description=(
        "Fetch real-time quotes for up to 50 stock or cryptocurrency symbols "
        "concurrently. Individual failures are reported in `failed_symbols` "
        "rather than failing the entire request."
    ),
    responses={
        200: {"description": "Quotes retrieved (partial success allowed)"},
        400: {"description": "Invalid request parameters"},
    },
)
async def get_batch_quotes(
    symbols: str = Query(
        ...,
        description="Comma-separated symbol list (max 50). E.g. AAPL,MSFT,BTC",
    ),
    source: Optional[str] = Query(
        None,
        description="Force a specific data source: finnhub, coingecko, yfinance",
    ),
) -> BatchQuoteResponse:
    """
    Batch quote endpoint.

    Fetches all symbols concurrently using asyncio.gather, so the total
    latency is roughly the slowest individual request.
    """
    if source and source not in VALID_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "ValidationError",
                "message": f"Invalid source '{source}'",
                "detail": {"allowed_values": sorted(VALID_SOURCES)},
            },
        )

    # Parse, strip, and deduplicate while preserving order
    raw = [s.strip() for s in symbols.split(",") if s.strip()]
    seen: set = set()
    symbol_list: List[str] = []
    for sym in raw:
        upper = sym.upper()
        if upper not in seen:
            seen.add(upper)
            symbol_list.append(sym)

    if not symbol_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "ValidationError",
                "message": "No valid symbols provided",
            },
        )

    if len(symbol_list) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "ValidationError",
                "message": f"Too many symbols ({len(symbol_list)}). Maximum is 50.",
            },
        )

    logger.info("batch_quote_request", count=len(symbol_list), symbols=symbol_list)

    async def _safe_fetch(sym: str) -> Tuple[str, Optional[Quote]]:
        """Fetch a single quote, swallowing any error."""
        try:
            quote = await _fetch_quote(sym, source)
            return sym, quote
        except HTTPException:
            return sym, None
        except Exception as exc:
            logger.error(
                "batch_quote_unexpected_error",
                symbol=sym,
                error=str(exc),
                exc_info=True,
            )
            return sym, None

    results = await asyncio.gather(*(_safe_fetch(sym) for sym in symbol_list))

    quotes: List[Quote] = []
    failed: List[str] = []
    for sym, quote in results:
        if quote is not None:
            quotes.append(quote)
        else:
            failed.append(sym.upper())

    logger.info(
        "batch_quote_complete",
        total=len(symbol_list),
        success=len(quotes),
        failed=len(failed),
    )

    return BatchQuoteResponse(
        quotes=quotes,
        count=len(quotes),
        failed_symbols=failed,
        timestamp=datetime.now(tz=timezone.utc),
    )


@router.get(
    "/{symbol}",
    response_model=Quote,
    summary="Get real-time quote",
    description=(
        "Fetch a real-time (or recently delayed) quote for a stock or "
        "cryptocurrency.\n\n"
        "**Stock fallback chain:** Finnhub → yfinance\n\n"
        "**Crypto fallback chain:** CoinGecko → yfinance\n\n"
        "Pass `source` to pin a specific data provider."
    ),
    responses={
        200: {"description": "Quote retrieved successfully"},
        400: {"description": "Invalid request parameters"},
        404: {"description": "Symbol not found"},
        429: {"description": "Rate limit exceeded"},
        503: {"description": "All data sources failed"},
    },
)
async def get_quote(
    symbol: str,
    source: Optional[str] = Query(
        None,
        description="Force a specific data source: finnhub, coingecko, yfinance",
    ),
) -> Quote:
    """
    Get a real-time quote for a stock or cryptocurrency.

    Asset type is auto-detected:
    - Known crypto symbols (BTC, ETH, etc.) → CoinGecko → yfinance fallback
    - CoinGecko IDs (lowercase, e.g. "bitcoin") → CoinGecko → yfinance
    - All other symbols treated as stocks → Finnhub → yfinance fallback
    """
    return await _fetch_quote(symbol, source)
