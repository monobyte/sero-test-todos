"""
Finnhub service for real-time stock data, company profiles, and WebSocket feeds.

Finnhub provides:
- REST API: Real-time US stock quotes, company profiles, historical candles
- WebSocket: Real-time US stock trade data (price, volume, timestamp)

Free tier limits (2026):
- REST: 60 API calls per minute
- WebSocket: Unlimited real-time US stock trades

API documentation: https://finnhub.io/docs/api

REST Base URL: https://finnhub.io/api/v1
WebSocket URL: wss://ws.finnhub.io?token=YOUR_TOKEN

Authentication:
- REST: ?token=YOUR_TOKEN query parameter
- WebSocket: ?token=YOUR_TOKEN in URL

Key REST Endpoints:
- GET /quote             → Real-time quote (c, d, dp, h, l, o, pc, t)
- GET /stock/profile2   → Company profile (name, exchange, industry, etc.)
- GET /stock/candle     → OHLCV historical candles

WebSocket message format (inbound trade data):
  {"type": "trade", "data": [{"s": "AAPL", "p": 150.25, "t": 1620000000000, "v": 100}]}

WebSocket subscribe/unsubscribe:
  {"type": "subscribe", "symbol": "AAPL"}
  {"type": "unsubscribe", "symbol": "AAPL"}
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

import websockets
from pydantic import BaseModel, Field

from config import settings
from models.market import AssetType, CompanyProfile, HistoricalData, OHLCV, Quote
from services.base import (
    AuthenticationError,
    BaseService,
    CacheType,
    NotFoundError,
    ServiceError,
)
from utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Finnhub-specific data models
# ---------------------------------------------------------------------------


class FinnhubTradeData(BaseModel):
    """A single real-time trade event received over the Finnhub WebSocket."""

    symbol: str = Field(..., description="Ticker symbol (e.g. AAPL)")
    price: float = Field(..., description="Trade price")
    volume: float = Field(..., description="Trade volume")
    timestamp: datetime = Field(..., description="Trade timestamp (UTC)")
    conditions: Optional[List[str]] = Field(None, description="Trade condition flags")

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "AAPL",
                "price": 150.25,
                "volume": 100.0,
                "timestamp": "2026-03-06T14:00:00Z",
                "conditions": None,
            }
        }


# ---------------------------------------------------------------------------
# Finnhub REST service
# ---------------------------------------------------------------------------


class FinnhubService(BaseService):
    """
    Finnhub REST API client for stock market data.

    Provides:
    - Real-time stock quotes  (GET /quote)
    - Company profiles        (GET /stock/profile2)
    - Historical OHLCV candles (GET /stock/candle)

    All responses are cached with appropriate TTLs:
    - Quotes:      60 s  (near-real-time)
    - Profiles:    24 h  (rarely changes)
    - Candles:      1 h  (intraday candles; daily candles rarely change)

    Authentication is injected via the ``token`` query parameter on every
    request — Finnhub does not use HTTP headers for auth.
    """

    SERVICE_NAME: str = "finnhub"
    BASE_URL: str = "https://finnhub.io/api/v1"

    # Finnhub free tier: 60 calls/min → we honour the global 50/min setting
    # and additionally observe the X-RateLimit-Remaining header

    # Candle resolution mapping: human-friendly → Finnhub resolution string
    RESOLUTION_MAP: Dict[str, str] = {
        "1m": "1",
        "5m": "5",
        "15m": "15",
        "30m": "30",
        "1h": "60",
        "1d": "D",
        "1w": "W",
        "1M": "M",
    }

    # ---------------------------------------------------------------------------
    # BaseService interface
    # ---------------------------------------------------------------------------

    def _get_base_url(self) -> str:
        return self.BASE_URL

    def _get_api_key(self) -> str:
        return settings.finnhub_api_key

    def _get_default_headers(self) -> Dict[str, str]:
        """Finnhub uses token query param; keep standard User-Agent."""
        return {
            "User-Agent": "MarketMonitor/0.1.0",
            "Accept": "application/json",
        }

    # ---------------------------------------------------------------------------
    # Public API methods
    # ---------------------------------------------------------------------------

    async def get_quote(self, symbol: str) -> Quote:
        """
        Fetch a real-time stock quote from Finnhub.

        Calls ``GET /quote?symbol=<SYMBOL>&token=<KEY>``.

        Finnhub response fields:
          c  – current price
          d  – change since previous close
          dp – percent change (%)
          h  – day high
          l  – day low
          o  – day open
          pc – previous close
          t  – UNIX timestamp of the quote

        Args:
            symbol: Ticker symbol (e.g. ``"AAPL"``).  Case-insensitive.

        Returns:
            :class:`~models.market.Quote` populated with live data.

        Raises:
            NotFoundError: If Finnhub returns a zero price (unknown symbol).
            AuthenticationError: If the API key is missing or invalid.
            RateLimitError: If the Finnhub rate limit is reached.
            ServiceError: For other unexpected API errors.
        """
        symbol = symbol.upper().strip()

        self._logger.info("get_quote", symbol=symbol)

        raw = await self._make_request(
            method="GET",
            endpoint="/quote",
            params={"symbol": symbol, "token": self._get_api_key()},
            cache_type=CacheType.QUOTE,
            cache_key_parts=["quote", symbol],
        )

        return self._parse_quote(symbol, raw)

    async def get_company_profile(self, symbol: str) -> CompanyProfile:
        """
        Fetch a company's profile from Finnhub.

        Calls ``GET /stock/profile2?symbol=<SYMBOL>&token=<KEY>``.

        Args:
            symbol: Ticker symbol (e.g. ``"AAPL"``).  Case-insensitive.

        Returns:
            :class:`~models.market.CompanyProfile` with metadata.

        Raises:
            NotFoundError: If Finnhub returns an empty profile (unknown symbol).
            AuthenticationError: If the API key is missing or invalid.
            RateLimitError: If the Finnhub rate limit is reached.
            ServiceError: For other unexpected API errors.
        """
        symbol = symbol.upper().strip()

        self._logger.info("get_company_profile", symbol=symbol)

        raw = await self._make_request(
            method="GET",
            endpoint="/stock/profile2",
            params={"symbol": symbol, "token": self._get_api_key()},
            cache_type=CacheType.FUNDAMENTAL,
            cache_key_parts=["profile", symbol],
        )

        return self._parse_company_profile(symbol, raw)

    async def get_candles(
        self,
        symbol: str,
        resolution: str = "D",
        from_timestamp: Optional[int] = None,
        to_timestamp: Optional[int] = None,
    ) -> HistoricalData:
        """
        Fetch OHLCV historical candle data from Finnhub.

        Calls ``GET /stock/candle`` with the given resolution and date range.

        Supported resolutions (Finnhub strings or human-friendly aliases):
            ``"1"`` / ``"1m"``   – 1 minute
            ``"5"`` / ``"5m"``   – 5 minutes
            ``"15"`` / ``"15m"`` – 15 minutes
            ``"30"`` / ``"30m"`` – 30 minutes
            ``"60"`` / ``"1h"``  – 1 hour
            ``"D"`` / ``"1d"``   – daily
            ``"W"`` / ``"1w"``   – weekly
            ``"M"`` / ``"1M"``   – monthly

        Args:
            symbol: Ticker symbol (e.g. ``"AAPL"``).
            resolution: Candle resolution.  Accepts Finnhub format or alias.
            from_timestamp: Start of range as UNIX epoch (seconds).
                            Defaults to 1 year ago.
            to_timestamp: End of range as UNIX epoch (seconds).
                          Defaults to now.

        Returns:
            :class:`~models.market.HistoricalData` with sorted candles.

        Raises:
            NotFoundError: If Finnhub returns ``"no_data"`` status.
            ServiceError: For other unexpected API errors.
        """
        symbol = symbol.upper().strip()

        # Normalise resolution alias → Finnhub string
        finnhub_resolution = self.RESOLUTION_MAP.get(resolution, resolution)

        # Default to last 1 year if no range specified
        now = int(datetime.now(tz=timezone.utc).timestamp())
        if to_timestamp is None:
            to_timestamp = now
        if from_timestamp is None:
            from_timestamp = now - 365 * 24 * 3600  # 1 year ago

        self._logger.info(
            "get_candles",
            symbol=symbol,
            resolution=finnhub_resolution,
            from_ts=from_timestamp,
            to_ts=to_timestamp,
        )

        raw = await self._make_request(
            method="GET",
            endpoint="/stock/candle",
            params={
                "symbol": symbol,
                "resolution": finnhub_resolution,
                "from": from_timestamp,
                "to": to_timestamp,
                "token": self._get_api_key(),
            },
            cache_type=CacheType.HISTORICAL,
            cache_key_parts=["candle", symbol, finnhub_resolution, str(from_timestamp)],
        )

        return self._parse_candles(symbol, finnhub_resolution, raw)

    # ---------------------------------------------------------------------------
    # Response parsers
    # ---------------------------------------------------------------------------

    def _parse_quote(self, symbol: str, data: Dict[str, Any]) -> Quote:
        """
        Convert a raw Finnhub ``/quote`` response dict into a :class:`Quote`.

        Finnhub returns a zero ``c`` (current price) when the symbol is not
        found, so we treat that as a not-found condition.

        Args:
            symbol: Ticker symbol (used for error messages and model field).
            data:   Raw JSON response from Finnhub.

        Returns:
            Populated :class:`~models.market.Quote`.

        Raises:
            NotFoundError: If current price is 0 (symbol not found).
            ServiceError: If the response is malformed.
        """
        if not data:
            raise NotFoundError(
                self.SERVICE_NAME,
                symbol,
                f"Empty response from Finnhub for symbol '{symbol}'",
            )

        current_price: float = data.get("c", 0.0) or 0.0

        if current_price == 0.0:
            raise NotFoundError(
                self.SERVICE_NAME,
                symbol,
                f"No quote data found for symbol '{symbol}' — it may be delisted or invalid",
            )

        # UNIX timestamp → UTC datetime
        raw_ts: Optional[int] = data.get("t")
        if raw_ts:
            quote_timestamp = datetime.fromtimestamp(raw_ts, tz=timezone.utc)
        else:
            quote_timestamp = datetime.now(tz=timezone.utc)

        self._logger.debug(
            "quote_parsed",
            symbol=symbol,
            price=current_price,
            change=data.get("d"),
            change_pct=data.get("dp"),
        )

        return Quote(
            symbol=symbol,
            asset_type=AssetType.STOCK,
            price=current_price,
            change=data.get("d") or 0.0,
            change_percent=data.get("dp") or 0.0,
            high_24h=data.get("h") or None,
            low_24h=data.get("l") or None,
            open_price=data.get("o") or None,
            previous_close=data.get("pc") or None,
            timestamp=quote_timestamp,
            source=self.SERVICE_NAME,
        )

    def _parse_company_profile(
        self, symbol: str, data: Dict[str, Any]
    ) -> CompanyProfile:
        """
        Convert a raw Finnhub ``/stock/profile2`` response into a
        :class:`CompanyProfile`.

        Finnhub returns an empty dict ``{}`` for unknown symbols rather than
        a 404, so we check for the ``ticker`` field.

        Args:
            symbol: Ticker symbol (used for fallback and error messages).
            data:   Raw JSON response from Finnhub.

        Returns:
            Populated :class:`~models.market.CompanyProfile`.

        Raises:
            NotFoundError: If the profile is empty (symbol not found).
        """
        if not data or not data.get("ticker"):
            raise NotFoundError(
                self.SERVICE_NAME,
                symbol,
                f"No company profile found for symbol '{symbol}'",
            )

        self._logger.debug("profile_parsed", symbol=symbol, name=data.get("name"))

        return CompanyProfile(
            symbol=data.get("ticker", symbol).upper(),
            name=data.get("name", ""),
            exchange=data.get("exchange") or None,
            country=data.get("country") or None,
            currency=data.get("currency") or None,
            industry=data.get("finnhubIndustry") or None,
            ipo_date=data.get("ipo") or None,
            market_cap=data.get("marketCapitalization") or None,
            shares_outstanding=data.get("shareOutstanding") or None,
            website=data.get("weburl") or None,
            logo=data.get("logo") or None,
            phone=data.get("phone") or None,
            source=self.SERVICE_NAME,
        )

    def _parse_candles(
        self, symbol: str, resolution: str, data: Dict[str, Any]
    ) -> HistoricalData:
        """
        Convert a raw Finnhub ``/stock/candle`` response into
        :class:`HistoricalData`.

        Finnhub candle response format:
          ``s``  – status string: ``"ok"`` or ``"no_data"``
          ``c``  – list of close prices
          ``h``  – list of high prices
          ``l``  – list of low prices
          ``o``  – list of open prices
          ``v``  – list of volume values
          ``t``  – list of UNIX timestamps (seconds)

        Args:
            symbol:     Ticker symbol.
            resolution: Finnhub resolution string (``"D"``, ``"60"``, etc.).
            data:       Raw JSON response from Finnhub.

        Returns:
            Populated :class:`~models.market.HistoricalData`.

        Raises:
            NotFoundError: If status is ``"no_data"`` or response is empty.
            ServiceError:  If response arrays have mismatched lengths.
        """
        if not data:
            raise NotFoundError(
                self.SERVICE_NAME,
                symbol,
                f"Empty candle response for symbol '{symbol}'",
            )

        status = data.get("s", "")
        if status == "no_data":
            raise NotFoundError(
                self.SERVICE_NAME,
                symbol,
                f"No historical candle data available for symbol '{symbol}'",
            )

        # Validate all required arrays are present and same length
        required_keys = ("c", "h", "l", "o", "v", "t")
        for key in required_keys:
            if key not in data:
                raise ServiceError(
                    message=f"Candle response missing field '{key}' for symbol '{symbol}'",
                    service=self.SERVICE_NAME,
                )

        lengths = {key: len(data[key]) for key in required_keys}
        if len(set(lengths.values())) > 1:
            raise ServiceError(
                message=(
                    f"Candle response arrays have mismatched lengths for '{symbol}': "
                    f"{lengths}"
                ),
                service=self.SERVICE_NAME,
            )

        # Build human-readable interval from Finnhub resolution
        resolution_to_interval = {v: k for k, v in self.RESOLUTION_MAP.items()}
        interval = resolution_to_interval.get(resolution, resolution.lower())

        candles: List[OHLCV] = [
            OHLCV(
                timestamp=datetime.fromtimestamp(data["t"][i], tz=timezone.utc),
                open=data["o"][i],
                high=data["h"][i],
                low=data["l"][i],
                close=data["c"][i],
                volume=data["v"][i],
            )
            for i in range(len(data["t"]))
        ]

        # Ensure chronological order
        candles.sort(key=lambda c: c.timestamp)

        self._logger.debug(
            "candles_parsed",
            symbol=symbol,
            resolution=resolution,
            candle_count=len(candles),
        )

        return HistoricalData(
            symbol=symbol,
            asset_type=AssetType.STOCK,
            interval=interval,
            candles=candles,
            source=self.SERVICE_NAME,
        )


# ---------------------------------------------------------------------------
# Finnhub WebSocket manager
# ---------------------------------------------------------------------------


class FinnhubWebSocketManager:
    """
    Manages a persistent WebSocket connection to the Finnhub real-time feed.

    The manager runs a background asyncio task that:
    1. Connects to ``wss://ws.finnhub.io?token=<KEY>``
    2. Subscribes to all currently-tracked symbols
    3. Dispatches received :class:`FinnhubTradeData` events to registered
       handler callbacks
    4. Automatically reconnects with exponential back-off on disconnection

    Usage example::

        manager = FinnhubWebSocketManager(api_key="YOUR_KEY")

        async def on_trade(trade: FinnhubTradeData) -> None:
            print(f"{trade.symbol}: ${trade.price}")

        manager.add_handler(on_trade)
        await manager.connect()
        await manager.subscribe("AAPL")
        await manager.subscribe("MSFT")

        # ... later ...
        await manager.unsubscribe("AAPL")
        await manager.disconnect()

    Handler callbacks must be **async** functions accepting a single
    :class:`FinnhubTradeData` argument.

    Thread safety:
        This class is not thread-safe and is designed for single-threaded
        asyncio use. All methods must be called from the same event loop.
    """

    WS_URL_TEMPLATE = "wss://ws.finnhub.io?token={token}"

    # Reconnect back-off: [1s, 2s, 4s, 8s, 16s, 30s] then cap at 30s
    RECONNECT_DELAYS = [1, 2, 4, 8, 16, 30]

    def __init__(self, api_key: str) -> None:
        """
        Initialise the manager.

        Args:
            api_key: Finnhub API key (same key used for REST calls).
        """
        self._api_key = api_key
        self._subscribed_symbols: Set[str] = set()
        self._handlers: List[Callable[[FinnhubTradeData], Any]] = []
        self._running: bool = False
        self._ws: Optional[Any] = None  # websockets.WebSocketClientProtocol
        self._task: Optional[asyncio.Task] = None
        self._logger = get_logger("services.finnhub.websocket")

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Return ``True`` if the WebSocket is currently open."""
        if self._ws is None:
            return False
        try:
            from websockets.protocol import State
            return self._ws.state is State.OPEN
        except AttributeError:
            # Fallback for older websockets versions
            return not getattr(self._ws, 'closed', True)

    @property
    def subscribed_symbols(self) -> Set[str]:
        """Return a copy of the set of currently-subscribed symbols."""
        return set(self._subscribed_symbols)

    async def connect(self) -> None:
        """
        Start the background WebSocket listener task.

        Idempotent — calling connect() when already running is a no-op.
        """
        if self._running:
            self._logger.debug("already_running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run(), name="finnhub-ws")
        self._logger.info("websocket_manager_started")

    async def disconnect(self) -> None:
        """
        Stop the background listener and close the WebSocket.

        Waits for the background task to finish (with a 5-second timeout).
        """
        self._running = False

        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        if self._task is not None:
            self._task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            self._task = None

        self._logger.info("websocket_manager_stopped")

    async def subscribe(self, symbol: str) -> None:
        """
        Subscribe to real-time trade data for *symbol*.

        If the WebSocket is already open, sends the subscribe message
        immediately.  Otherwise the symbol is recorded and sent upon
        the next successful connection.

        Args:
            symbol: Ticker symbol (case-insensitive).
        """
        symbol = symbol.upper().strip()
        self._subscribed_symbols.add(symbol)
        self._logger.info("subscribe_requested", symbol=symbol)

        if self.is_connected:
            await self._send_subscribe(symbol)

    async def unsubscribe(self, symbol: str) -> None:
        """
        Unsubscribe from real-time trade data for *symbol*.

        Args:
            symbol: Ticker symbol (case-insensitive).
        """
        symbol = symbol.upper().strip()
        self._subscribed_symbols.discard(symbol)
        self._logger.info("unsubscribe_requested", symbol=symbol)

        if self.is_connected:
            await self._send_unsubscribe(symbol)

    def add_handler(self, handler: Callable[[FinnhubTradeData], Any]) -> None:
        """
        Register an async callback to receive :class:`FinnhubTradeData` events.

        Args:
            handler: Async function with signature
                     ``async def handler(trade: FinnhubTradeData) -> None``.
        """
        if handler not in self._handlers:
            self._handlers.append(handler)
            self._logger.debug("handler_registered", handler=handler.__name__)

    def remove_handler(self, handler: Callable[[FinnhubTradeData], Any]) -> None:
        """
        Remove a previously-registered handler.

        Args:
            handler: The handler to remove.  No-op if not registered.
        """
        try:
            self._handlers.remove(handler)
            self._logger.debug("handler_removed", handler=handler.__name__)
        except ValueError:
            pass

    # ------------------------------------------------------------------
    # Internal background loop
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        """
        Background task: connect → subscribe → listen → reconnect.

        Runs until ``self._running`` is set to ``False``.
        """
        attempt = 0

        while self._running:
            try:
                ws_url = self.WS_URL_TEMPLATE.format(token=self._api_key)

                self._logger.info(
                    "websocket_connecting",
                    url=ws_url.replace(self._api_key, "***"),
                    attempt=attempt + 1,
                )

                async with websockets.connect(
                    ws_url,
                    ping_interval=settings.ws_ping_interval,
                    ping_timeout=settings.ws_ping_timeout,
                ) as ws:
                    self._ws = ws
                    attempt = 0  # Reset back-off on successful connection

                    self._logger.info("websocket_connected")

                    # Re-subscribe to all tracked symbols after (re-)connect
                    for symbol in list(self._subscribed_symbols):
                        await self._send_subscribe(symbol)

                    # Message loop
                    async for raw_message in ws:
                        if not self._running:
                            break
                        await self._handle_message(raw_message)

            except asyncio.CancelledError:
                self._logger.debug("websocket_task_cancelled")
                break

            except (
                websockets.exceptions.InvalidStatus,
                websockets.exceptions.InvalidStatusCode,  # deprecated alias
            ) as exc:
                # 401 = bad API key; no point retrying
                status = getattr(exc, 'response', None)
                status_code = getattr(status, 'status_code', None) or getattr(exc, 'status_code', None)
                if status_code == 401:
                    self._logger.error(
                        "websocket_auth_failed",
                        status_code=status_code,
                    )
                    self._running = False
                    break

                self._logger.warning(
                    "websocket_error",
                    error=str(exc),
                    attempt=attempt + 1,
                )

            except Exception as exc:
                self._logger.warning(
                    "websocket_disconnected",
                    error=str(exc),
                    attempt=attempt + 1,
                )

            finally:
                self._ws = None

            # Back-off before reconnecting
            if self._running:
                delay = self.RECONNECT_DELAYS[
                    min(attempt, len(self.RECONNECT_DELAYS) - 1)
                ]
                self._logger.info("websocket_reconnecting", delay=delay)
                await asyncio.sleep(delay)
                attempt += 1

        self._logger.info("websocket_run_loop_exited")

    # ------------------------------------------------------------------
    # WebSocket protocol helpers
    # ------------------------------------------------------------------

    async def _send_subscribe(self, symbol: str) -> None:
        """Send a Finnhub subscribe message for *symbol*."""
        if not self.is_connected:
            return
        msg = json.dumps({"type": "subscribe", "symbol": symbol})
        try:
            await self._ws.send(msg)
            self._logger.debug("subscribed", symbol=symbol)
        except Exception as exc:
            self._logger.warning("subscribe_failed", symbol=symbol, error=str(exc))

    async def _send_unsubscribe(self, symbol: str) -> None:
        """Send a Finnhub unsubscribe message for *symbol*."""
        if not self.is_connected:
            return
        msg = json.dumps({"type": "unsubscribe", "symbol": symbol})
        try:
            await self._ws.send(msg)
            self._logger.debug("unsubscribed", symbol=symbol)
        except Exception as exc:
            self._logger.warning("unsubscribe_failed", symbol=symbol, error=str(exc))

    async def _handle_message(self, raw_message: str) -> None:
        """
        Parse an inbound WebSocket message and dispatch to handlers.

        Finnhub message types:
        - ``"trade"``  – contains ``data`` array of trade objects
        - ``"ping"``   – keepalive ping; we respond with ``{"type":"pong"}``

        Unknown message types are silently ignored (logged at DEBUG level).

        Args:
            raw_message: Raw JSON string received from Finnhub.
        """
        try:
            envelope = json.loads(raw_message)
        except json.JSONDecodeError as exc:
            self._logger.warning("invalid_json", error=str(exc))
            return

        msg_type = envelope.get("type")

        if msg_type == "trade":
            trade_list = envelope.get("data") or []
            for raw_trade in trade_list:
                trade_data = self._parse_trade(raw_trade)
                if trade_data is None:
                    continue
                # Dispatch to all handlers (each in its own task so a slow
                # handler never delays the message loop)
                for handler in list(self._handlers):
                    asyncio.create_task(
                        self._call_handler(handler, trade_data),
                        name=f"finnhub-handler-{handler.__name__}",
                    )

        elif msg_type == "ping":
            # Respond with pong to keep the connection alive
            try:
                await self._ws.send(json.dumps({"type": "pong"}))
            except Exception:
                pass

        else:
            self._logger.debug("unknown_message_type", msg_type=msg_type)

    def _parse_trade(self, raw: Dict[str, Any]) -> Optional[FinnhubTradeData]:
        """
        Convert a raw trade dict from the Finnhub WebSocket into a
        :class:`FinnhubTradeData` instance.

        Finnhub trade object fields:
          ``s`` – symbol
          ``p`` – price
          ``t`` – UNIX timestamp in **milliseconds**
          ``v`` – volume
          ``c`` – list of condition strings (optional)

        Args:
            raw: Single trade dict from the ``data`` array.

        Returns:
            :class:`FinnhubTradeData` or ``None`` if parsing fails.
        """
        try:
            symbol: str = raw["s"]
            price: float = float(raw["p"])
            timestamp_ms: int = int(raw["t"])
            volume: float = float(raw.get("v", 0.0))
            conditions: Optional[List[str]] = raw.get("c") or None

            timestamp = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)

            return FinnhubTradeData(
                symbol=symbol,
                price=price,
                volume=volume,
                timestamp=timestamp,
                conditions=conditions,
            )
        except (KeyError, ValueError, TypeError) as exc:
            self._logger.warning("trade_parse_error", raw=raw, error=str(exc))
            return None

    @staticmethod
    async def _call_handler(
        handler: Callable[[FinnhubTradeData], Any],
        trade_data: FinnhubTradeData,
    ) -> None:
        """
        Safely invoke a single handler, catching and logging any exceptions.

        Args:
            handler:    Async callable.
            trade_data: Trade data to pass to the handler.
        """
        try:
            await handler(trade_data)
        except Exception as exc:
            logger.warning(
                "handler_exception",
                handler=handler.__name__,
                error=str(exc),
            )


# ---------------------------------------------------------------------------
# Module-level singleton helpers
# ---------------------------------------------------------------------------

# Lazily-created module-level instances (created on first access)
_finnhub_service: Optional[FinnhubService] = None
_ws_manager: Optional[FinnhubWebSocketManager] = None


def get_finnhub_service() -> FinnhubService:
    """
    Return the module-level :class:`FinnhubService` singleton.

    Creates the instance on first call.
    """
    global _finnhub_service
    if _finnhub_service is None:
        _finnhub_service = FinnhubService()
    return _finnhub_service


def get_ws_manager() -> FinnhubWebSocketManager:
    """
    Return the module-level :class:`FinnhubWebSocketManager` singleton.

    Creates the instance on first call using the configured API key.
    """
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = FinnhubWebSocketManager(api_key=settings.finnhub_api_key)
    return _ws_manager
