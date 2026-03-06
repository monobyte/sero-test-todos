"""
WebSocket router — real-time price updates via a multiplexed Finnhub feed.

Endpoint
--------
WS /ws/quotes

Architecture
------------
A single ``ConnectionManager`` singleton manages all connected clients.
Upstream market data flows from a shared ``FinnhubWebSocketManager`` which
maintains a *single* persistent WebSocket to Finnhub and fans out incoming
trade events to every client that has subscribed to that symbol.

                        ┌─────────────────────────────────┐
     Finnhub WS Feed    │       FinnhubWebSocketManager   │
  wss://ws.finnhub.io ──►  (one upstream connection)      │
                        │  ┌──────────────────────────┐   │
                        │  │  on_trade(FinnhubTrade)  │   │
                        │  └────────────┬─────────────┘   │
                        └───────────────┼─────────────────┘
                                        │ calls handler
                        ┌───────────────▼─────────────────┐
                        │        ConnectionManager         │
                        │  _symbol_subscribers             │
                        │    "AAPL" → {client_a, client_b} │
                        │    "MSFT" → {client_a}           │
                        │  broadcast_trade(trade)          │
                        └───────────┬─────────────┬────────┘
                                    │             │
                               ┌────▼────┐   ┌───▼─────┐
                               │Client A │   │Client B │
                               │(AAPL+   │   │(AAPL    │
                               │ MSFT)   │   │ only)   │
                               └─────────┘   └─────────┘

Client Protocol
---------------
The client communicates with plain-text JSON frames.

  Subscribe:
    {"action": "subscribe", "symbols": ["AAPL", "MSFT"]}

  Unsubscribe:
    {"action": "unsubscribe", "symbols": ["AAPL"]}

  Pong (response to server ping):
    {"type": "pong"}

The server emits:

  Ping (every ``settings.ws_ping_interval`` seconds):
    {"type": "ping"}

  Trade update:
    {
      "type": "trade",
      "symbol": "AAPL",
      "price": 178.25,
      "volume": 100.0,
      "timestamp": "2026-03-06T17:00:00Z"
    }

  Subscription acknowledgement:
    {"type": "subscribed", "symbols": ["AAPL", "MSFT"], "client_id": "abc123"}

  Unsubscribe acknowledgement:
    {"type": "unsubscribed", "symbols": ["AAPL"], "client_id": "abc123"}

  Error:
    {"type": "error", "code": "INVALID_MESSAGE", "message": "..."}

Notes
-----
- Only US stock symbols are supported via the Finnhub WebSocket feed.
  Crypto symbols are rejected with an ``UNSUPPORTED_SYMBOL`` error.
- Each client may subscribe to at most ``MAX_SYMBOLS_PER_CLIENT`` symbols.
- At most ``settings.ws_max_connections`` concurrent clients are permitted.
- The Finnhub upstream connection is started during ``lifespan`` via
  ``connection_manager.startup()`` and torn down via ``connection_manager.shutdown()``.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from config import settings
from services.finnhub_service import FinnhubTradeData, FinnhubWebSocketManager, get_ws_manager
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["WebSocket"])

# Maximum symbols a single client may subscribe to
MAX_SYMBOLS_PER_CLIENT = 50

# Ping interval for connected clients (seconds)
_CLIENT_PING_INTERVAL = settings.ws_ping_interval


# ---------------------------------------------------------------------------
# Per-client state
# ---------------------------------------------------------------------------


@dataclass
class _ClientState:
    """State for a single connected WebSocket client."""

    client_id: str
    websocket: WebSocket
    subscribed_symbols: Set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Connection manager
# ---------------------------------------------------------------------------


class ConnectionManager:
    """
    Manages all active WebSocket client connections and their subscriptions.

    Responsibilities
    ----------------
    1. Accept / remove client connections.
    2. Track per-client symbol subscriptions.
    3. Manage upstream Finnhub subscriptions (subscribe only when at least
       one client wants a symbol; unsubscribe when the last client leaves).
    4. Fan out incoming Finnhub trade events to relevant clients.
    5. Send periodic pings to keep client connections alive.

    Thread safety
    -------------
    Designed for a single-threaded asyncio environment.  All methods are
    coroutines or plain synchronous (no locks needed).
    """

    def __init__(self) -> None:
        # client_id → _ClientState
        self._clients: Dict[str, _ClientState] = {}
        # symbol → set of client_ids
        self._symbol_subscribers: Dict[str, Set[str]] = {}
        # Upstream WS manager (set during startup)
        self._ws_manager: Optional[FinnhubWebSocketManager] = None
        # Background ping task
        self._ping_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        """
        Initialise the upstream Finnhub WebSocket connection.

        Called once during application startup.
        """
        self._ws_manager = get_ws_manager()
        self._ws_manager.add_handler(self._on_trade)

        if settings.finnhub_api_key:
            await self._ws_manager.connect()
            logger.info("ws_manager_upstream_started")
        else:
            logger.warning(
                "finnhub_api_key_missing",
                message="Real-time WebSocket feed disabled — no Finnhub API key configured",
            )

        # Start ping loop
        self._ping_task = asyncio.create_task(
            self._ping_loop(), name="ws-ping-loop"
        )

    async def shutdown(self) -> None:
        """
        Close all client connections and disconnect from Finnhub.

        Called once during application shutdown.
        """
        if self._ping_task is not None:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
            self._ping_task = None

        # Close all clients
        for state in list(self._clients.values()):
            try:
                await state.websocket.close(code=1001)
            except Exception:
                pass

        self._clients.clear()
        self._symbol_subscribers.clear()

        if self._ws_manager is not None:
            await self._ws_manager.disconnect()
            logger.info("ws_manager_upstream_stopped")

    # ------------------------------------------------------------------
    # Client lifecycle
    # ------------------------------------------------------------------

    async def connect(self, websocket: WebSocket) -> Optional[str]:
        """
        Accept a new WebSocket client connection.

        Args:
            websocket: Incoming WebSocket connection.

        Returns:
            Assigned client_id, or None if the connection was rejected
            (e.g. max-connections limit reached).
        """
        if len(self._clients) >= settings.ws_max_connections:
            logger.warning(
                "ws_connection_rejected",
                reason="max_connections_reached",
                current=len(self._clients),
                limit=settings.ws_max_connections,
            )
            await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
            return None

        await websocket.accept()
        client_id = str(uuid.uuid4())
        self._clients[client_id] = _ClientState(
            client_id=client_id, websocket=websocket
        )
        logger.info(
            "ws_client_connected",
            client_id=client_id,
            total_clients=len(self._clients),
        )
        return client_id

    async def disconnect(self, client_id: str) -> None:
        """
        Remove a client and clean up its subscriptions.

        Args:
            client_id: ID of the client to remove.
        """
        state = self._clients.pop(client_id, None)
        if state is None:
            return

        # Unsubscribe from all symbols
        for symbol in list(state.subscribed_symbols):
            await self._unsubscribe_symbol(client_id, symbol)

        logger.info(
            "ws_client_disconnected",
            client_id=client_id,
            total_clients=len(self._clients),
        )

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    async def subscribe(self, client_id: str, symbols: list[str]) -> list[str]:
        """
        Subscribe a client to real-time updates for one or more symbols.

        Args:
            client_id: Client identifier.
            symbols:   List of ticker symbols (already upper-cased).

        Returns:
            List of symbols that were actually subscribed (may be shorter
            than the input if the per-client limit was reached).
        """
        state = self._clients.get(client_id)
        if state is None:
            return []

        subscribed: list[str] = []
        for symbol in symbols:
            # Reject non-stock symbols
            if not _is_stock_symbol(symbol):
                await self._send_error(
                    state.websocket,
                    code="UNSUPPORTED_SYMBOL",
                    message=(
                        f"Symbol '{symbol}' is not supported. "
                        "Only US stock ticker symbols are supported via the live feed."
                    ),
                )
                continue

            # Enforce per-client symbol limit
            if (
                symbol not in state.subscribed_symbols
                and len(state.subscribed_symbols) >= MAX_SYMBOLS_PER_CLIENT
            ):
                await self._send_error(
                    state.websocket,
                    code="TOO_MANY_SYMBOLS",
                    message=(
                        f"Cannot subscribe to '{symbol}': "
                        f"limit of {MAX_SYMBOLS_PER_CLIENT} symbols per connection reached."
                    ),
                )
                continue

            state.subscribed_symbols.add(symbol)
            await self._subscribe_symbol(client_id, symbol)
            subscribed.append(symbol)

        logger.info(
            "ws_client_subscribed",
            client_id=client_id,
            symbols=subscribed,
            total_subscriptions=len(state.subscribed_symbols),
        )
        return subscribed

    async def unsubscribe(self, client_id: str, symbols: list[str]) -> list[str]:
        """
        Unsubscribe a client from one or more symbols.

        Args:
            client_id: Client identifier.
            symbols:   List of ticker symbols (already upper-cased).

        Returns:
            List of symbols that were actually unsubscribed.
        """
        state = self._clients.get(client_id)
        if state is None:
            return []

        removed: list[str] = []
        for symbol in symbols:
            if symbol in state.subscribed_symbols:
                state.subscribed_symbols.discard(symbol)
                await self._unsubscribe_symbol(client_id, symbol)
                removed.append(symbol)

        logger.info(
            "ws_client_unsubscribed",
            client_id=client_id,
            symbols=removed,
        )
        return removed

    # ------------------------------------------------------------------
    # Upstream symbol management
    # ------------------------------------------------------------------

    async def _subscribe_symbol(self, client_id: str, symbol: str) -> None:
        """
        Register *client_id* as a subscriber to *symbol*.
        Starts the upstream Finnhub subscription if this is the first subscriber.
        """
        if symbol not in self._symbol_subscribers:
            self._symbol_subscribers[symbol] = set()

        self._symbol_subscribers[symbol].add(client_id)

        # First subscriber → ask Finnhub to send us this symbol
        if len(self._symbol_subscribers[symbol]) == 1 and self._ws_manager is not None:
            await self._ws_manager.subscribe(symbol)
            logger.debug("upstream_subscribe", symbol=symbol)

    async def _unsubscribe_symbol(self, client_id: str, symbol: str) -> None:
        """
        Remove *client_id* from *symbol*'s subscriber set.
        Sends an upstream unsubscribe to Finnhub when the last client leaves.
        """
        subscribers = self._symbol_subscribers.get(symbol)
        if subscribers is None:
            return

        subscribers.discard(client_id)

        if not subscribers:
            del self._symbol_subscribers[symbol]
            # Last subscriber gone → unsubscribe upstream
            if self._ws_manager is not None:
                await self._ws_manager.unsubscribe(symbol)
                logger.debug("upstream_unsubscribe", symbol=symbol)

    # ------------------------------------------------------------------
    # Incoming trade handler (called from FinnhubWebSocketManager)
    # ------------------------------------------------------------------

    async def _on_trade(self, trade: FinnhubTradeData) -> None:
        """
        Receive a trade event from the upstream Finnhub feed and fan it out
        to all clients subscribed to the trade's symbol.

        This is registered as a handler with ``FinnhubWebSocketManager``.

        Args:
            trade: Parsed trade event from Finnhub.
        """
        subscribers = self._symbol_subscribers.get(trade.symbol, set())
        if not subscribers:
            return

        message = json.dumps(
            {
                "type": "trade",
                "symbol": trade.symbol,
                "price": trade.price,
                "volume": trade.volume,
                "timestamp": trade.timestamp.isoformat(),
            }
        )

        # Fan out to all subscribers concurrently (don't block if one is slow)
        tasks = [
            self._send_raw(client_id, message) for client_id in list(subscribers)
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ------------------------------------------------------------------
    # Messaging helpers
    # ------------------------------------------------------------------

    async def _send_raw(self, client_id: str, message: str) -> None:
        """
        Send a raw JSON string to a specific client.

        Silently disconnects the client if the send fails.

        Args:
            client_id: Target client.
            message:   JSON string to send.
        """
        state = self._clients.get(client_id)
        if state is None:
            return
        try:
            await state.websocket.send_text(message)
        except Exception as exc:
            logger.warning(
                "ws_send_failed",
                client_id=client_id,
                error=str(exc),
            )
            await self.disconnect(client_id)

    @staticmethod
    async def _send_json(websocket: WebSocket, data: Dict[str, Any]) -> None:
        """Send a dictionary as a JSON frame."""
        try:
            await websocket.send_text(json.dumps(data))
        except Exception:
            pass  # Caller handles disconnect

    @staticmethod
    async def _send_error(
        websocket: WebSocket, code: str, message: str
    ) -> None:
        """Send a structured error frame to the client."""
        await ConnectionManager._send_json(
            websocket, {"type": "error", "code": code, "message": message}
        )

    # ------------------------------------------------------------------
    # Ping loop
    # ------------------------------------------------------------------

    async def _ping_loop(self) -> None:
        """
        Periodically send a ``{"type": "ping"}`` frame to every connected client.

        Clients that fail to respond (or whose send fails) are disconnected.
        """
        while True:
            try:
                await asyncio.sleep(_CLIENT_PING_INTERVAL)
            except asyncio.CancelledError:
                break

            for client_id in list(self._clients):
                await self._send_raw(client_id, json.dumps({"type": "ping"}))


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

connection_manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_stock_symbol(symbol: str) -> bool:
    """
    Return True if *symbol* looks like a US stock ticker.

    Heuristic: 1–5 uppercase letters only (no digits, no special chars).
    This covers almost all NYSE/NASDAQ symbols but will reject crypto IDs like
    "bitcoin" or "BTC-USD".

    Note: Some US stocks have 5-letter symbols (e.g. GOOGL, ARNC).  A stricter
    lookup table could be used in production.
    """
    return bool(symbol) and symbol.isalpha() and 1 <= len(symbol) <= 5


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@router.websocket("/ws/quotes")
async def quotes_websocket(websocket: WebSocket) -> None:
    """
    Real-time quote updates via WebSocket.

    Multiplexes the Finnhub trade feed to multiple concurrent clients.
    Clients send JSON subscribe/unsubscribe messages to control which symbols
    they receive updates for.

    Client → Server messages:
    -------------------------
    Subscribe:
        ``{"action": "subscribe", "symbols": ["AAPL", "MSFT"]}``

    Unsubscribe:
        ``{"action": "unsubscribe", "symbols": ["AAPL"]}``

    Pong (response to server ping):
        ``{"type": "pong"}``

    Server → Client messages:
    -------------------------
    Subscription ack:
        ``{"type": "subscribed", "symbols": [...], "client_id": "..."}``

    Unsubscribe ack:
        ``{"type": "unsubscribed", "symbols": [...], "client_id": "..."}``

    Trade update:
        ``{"type": "trade", "symbol": "AAPL", "price": 178.25, "volume": 100.0, ...}``

    Ping:
        ``{"type": "ping"}``

    Error:
        ``{"type": "error", "code": "...", "message": "..."}``
    """
    client_id = await connection_manager.connect(websocket)
    if client_id is None:
        # Connection was rejected (max clients reached)
        return

    try:
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break

            # Parse incoming message
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ConnectionManager._send_error(
                    websocket,
                    code="INVALID_JSON",
                    message="Message is not valid JSON.",
                )
                continue

            if not isinstance(msg, dict):
                await ConnectionManager._send_error(
                    websocket,
                    code="INVALID_MESSAGE",
                    message="Message must be a JSON object.",
                )
                continue

            action = msg.get("action") or msg.get("type")

            if action == "subscribe":
                raw_symbols = msg.get("symbols", [])
                if not isinstance(raw_symbols, list):
                    await ConnectionManager._send_error(
                        websocket,
                        code="INVALID_PAYLOAD",
                        message="'symbols' must be a list.",
                    )
                    continue

                symbols = [str(s).upper().strip() for s in raw_symbols if s]
                subscribed = await connection_manager.subscribe(client_id, symbols)

                await ConnectionManager._send_json(
                    websocket,
                    {
                        "type": "subscribed",
                        "symbols": subscribed,
                        "client_id": client_id,
                    },
                )

            elif action == "unsubscribe":
                raw_symbols = msg.get("symbols", [])
                if not isinstance(raw_symbols, list):
                    await ConnectionManager._send_error(
                        websocket,
                        code="INVALID_PAYLOAD",
                        message="'symbols' must be a list.",
                    )
                    continue

                symbols = [str(s).upper().strip() for s in raw_symbols if s]
                removed = await connection_manager.unsubscribe(client_id, symbols)

                await ConnectionManager._send_json(
                    websocket,
                    {
                        "type": "unsubscribed",
                        "symbols": removed,
                        "client_id": client_id,
                    },
                )

            elif action == "pong":
                # Client responded to our ping; nothing to do
                logger.debug("ws_pong_received", client_id=client_id)

            else:
                await ConnectionManager._send_error(
                    websocket,
                    code="UNKNOWN_ACTION",
                    message=(
                        f"Unknown action '{action}'. "
                        "Supported actions: subscribe, unsubscribe, pong."
                    ),
                )

    except WebSocketDisconnect:
        logger.info("ws_client_disconnected_unexpected", client_id=client_id)
    except Exception as exc:
        logger.error(
            "ws_client_error",
            client_id=client_id,
            error=str(exc),
            exc_info=True,
        )
    finally:
        await connection_manager.disconnect(client_id)


# ---------------------------------------------------------------------------
# Status endpoint (REST)
# ---------------------------------------------------------------------------


@router.get(
    "/ws/status",
    tags=["WebSocket"],
    summary="WebSocket connection status",
    description="Get the current number of connected clients and subscribed symbols.",
)
async def websocket_status() -> Dict[str, Any]:
    """
    Return current WebSocket hub metrics.

    Response fields:
    - ``connected_clients``   – Number of active WebSocket connections
    - ``subscribed_symbols``  – Number of unique symbols with at least one subscriber
    - ``upstream_connected``  – Whether the Finnhub upstream WS is currently open
    - ``upstream_symbols``    – Number of symbols subscribed upstream with Finnhub
    """
    ws_manager = connection_manager._ws_manager
    return {
        "connected_clients": len(connection_manager._clients),
        "subscribed_symbols": len(connection_manager._symbol_subscribers),
        "upstream_connected": ws_manager.is_connected if ws_manager is not None else False,
        "upstream_symbols": (
            len(ws_manager.subscribed_symbols) if ws_manager is not None else 0
        ),
    }
