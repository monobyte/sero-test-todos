"""
Tests for the WebSocket router and ConnectionManager.

Covers:
- ConnectionManager: connect, disconnect, subscribe, unsubscribe
- Symbol validation (_is_stock_symbol)
- Upstream subscription management (subscribe first client / unsubscribe last)
- Ping loop behaviour
- WebSocket endpoint: subscribe/unsubscribe/unknown action/pong flow
- GET /ws/status endpoint
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketState


# ---------------------------------------------------------------------------
# Helpers / unit tests for _is_stock_symbol
# ---------------------------------------------------------------------------


class TestIsStockSymbol:
    """Unit tests for the _is_stock_symbol helper."""

    def test_valid_symbols(self):
        from routers.websocket import _is_stock_symbol

        for sym in ["AAPL", "MSFT", "GOOGL", "V", "T"]:
            assert _is_stock_symbol(sym), f"{sym} should be valid"

    def test_invalid_crypto(self):
        from routers.websocket import _is_stock_symbol

        for sym in ["BTC-USD", "bitcoin", "ETH2", "123ABC", ""]:
            assert not _is_stock_symbol(sym), f"{sym} should be invalid"

    def test_too_long(self):
        from routers.websocket import _is_stock_symbol

        assert not _is_stock_symbol("TOOLONGSYM")

    def test_empty_string(self):
        from routers.websocket import _is_stock_symbol

        assert not _is_stock_symbol("")


# ---------------------------------------------------------------------------
# ConnectionManager unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestConnectionManager:
    """Async unit tests for ConnectionManager."""

    def _make_mock_websocket(self) -> MagicMock:
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.close = AsyncMock()
        ws.send_text = AsyncMock()
        ws.receive_text = AsyncMock()
        ws.client_state = WebSocketState.CONNECTED
        return ws

    def _make_mock_ws_manager(self) -> MagicMock:
        mgr = MagicMock()
        mgr.is_connected = True
        mgr.subscribed_symbols = set()
        mgr.add_handler = MagicMock()
        mgr.connect = AsyncMock()
        mgr.disconnect = AsyncMock()
        mgr.subscribe = AsyncMock()
        mgr.unsubscribe = AsyncMock()
        return mgr

    async def test_connect_accepts_websocket(self):
        from routers.websocket import ConnectionManager

        manager = ConnectionManager()
        ws = self._make_mock_websocket()
        client_id = await manager.connect(ws)

        ws.accept.assert_called_once()
        assert client_id is not None
        assert client_id in manager._clients

    async def test_connect_rejects_when_at_max(self):
        from config import settings
        from routers.websocket import ConnectionManager

        manager = ConnectionManager()
        # Fill up to max
        for _ in range(settings.ws_max_connections):
            ws = self._make_mock_websocket()
            cid = await manager.connect(ws)
            assert cid is not None

        # This one should be rejected
        ws_extra = self._make_mock_websocket()
        result = await manager.connect(ws_extra)
        assert result is None
        ws_extra.close.assert_called_once()

    async def test_disconnect_cleans_up_client(self):
        from routers.websocket import ConnectionManager

        manager = ConnectionManager()
        ws = self._make_mock_websocket()
        client_id = await manager.connect(ws)
        assert client_id in manager._clients

        await manager.disconnect(client_id)
        assert client_id not in manager._clients

    async def test_subscribe_adds_to_state(self):
        from routers.websocket import ConnectionManager

        manager = ConnectionManager()
        manager._ws_manager = self._make_mock_ws_manager()

        ws = self._make_mock_websocket()
        client_id = await manager.connect(ws)

        subscribed = await manager.subscribe(client_id, ["AAPL", "MSFT"])
        assert "AAPL" in subscribed
        assert "MSFT" in subscribed
        assert "AAPL" in manager._clients[client_id].subscribed_symbols
        assert "MSFT" in manager._clients[client_id].subscribed_symbols

    async def test_subscribe_calls_upstream(self):
        from routers.websocket import ConnectionManager

        manager = ConnectionManager()
        ws_mgr = self._make_mock_ws_manager()
        manager._ws_manager = ws_mgr

        ws = self._make_mock_websocket()
        client_id = await manager.connect(ws)

        await manager.subscribe(client_id, ["AAPL"])
        ws_mgr.subscribe.assert_called_once_with("AAPL")

    async def test_subscribe_does_not_double_subscribe_upstream(self):
        """Second client subscribing to same symbol → no second upstream subscribe."""
        from routers.websocket import ConnectionManager

        manager = ConnectionManager()
        ws_mgr = self._make_mock_ws_manager()
        manager._ws_manager = ws_mgr

        ws1 = self._make_mock_websocket()
        ws2 = self._make_mock_websocket()
        cid1 = await manager.connect(ws1)
        cid2 = await manager.connect(ws2)

        await manager.subscribe(cid1, ["AAPL"])
        await manager.subscribe(cid2, ["AAPL"])

        # upstream.subscribe should only be called once
        ws_mgr.subscribe.assert_called_once_with("AAPL")

    async def test_unsubscribe_removes_from_state(self):
        from routers.websocket import ConnectionManager

        manager = ConnectionManager()
        ws_mgr = self._make_mock_ws_manager()
        manager._ws_manager = ws_mgr

        ws = self._make_mock_websocket()
        client_id = await manager.connect(ws)
        await manager.subscribe(client_id, ["AAPL"])

        removed = await manager.unsubscribe(client_id, ["AAPL"])
        assert "AAPL" in removed
        assert "AAPL" not in manager._clients[client_id].subscribed_symbols

    async def test_unsubscribe_calls_upstream_when_last_subscriber(self):
        from routers.websocket import ConnectionManager

        manager = ConnectionManager()
        ws_mgr = self._make_mock_ws_manager()
        manager._ws_manager = ws_mgr

        ws = self._make_mock_websocket()
        client_id = await manager.connect(ws)
        await manager.subscribe(client_id, ["AAPL"])
        await manager.unsubscribe(client_id, ["AAPL"])

        ws_mgr.unsubscribe.assert_called_once_with("AAPL")

    async def test_unsubscribe_does_not_call_upstream_while_others_subscribed(self):
        from routers.websocket import ConnectionManager

        manager = ConnectionManager()
        ws_mgr = self._make_mock_ws_manager()
        manager._ws_manager = ws_mgr

        ws1 = self._make_mock_websocket()
        ws2 = self._make_mock_websocket()
        cid1 = await manager.connect(ws1)
        cid2 = await manager.connect(ws2)

        await manager.subscribe(cid1, ["AAPL"])
        await manager.subscribe(cid2, ["AAPL"])

        # Only cid1 unsubscribes; cid2 still watching AAPL
        await manager.unsubscribe(cid1, ["AAPL"])
        ws_mgr.unsubscribe.assert_not_called()

    async def test_rejects_non_stock_symbol(self):
        from routers.websocket import ConnectionManager

        manager = ConnectionManager()
        manager._ws_manager = self._make_mock_ws_manager()

        ws = self._make_mock_websocket()
        client_id = await manager.connect(ws)

        subscribed = await manager.subscribe(client_id, ["bitcoin"])
        assert "bitcoin" not in subscribed
        # Should have sent an error frame
        ws.send_text.assert_called_once()
        payload = json.loads(ws.send_text.call_args[0][0])
        assert payload["type"] == "error"
        assert payload["code"] == "UNSUPPORTED_SYMBOL"

    async def test_enforces_per_client_symbol_limit(self):
        from routers.websocket import ConnectionManager, MAX_SYMBOLS_PER_CLIENT

        manager = ConnectionManager()
        manager._ws_manager = self._make_mock_ws_manager()

        ws = self._make_mock_websocket()
        client_id = await manager.connect(ws)

        # Generate MAX_SYMBOLS_PER_CLIENT unique all-alpha symbols (1-5 letters)
        # that pass _is_stock_symbol (letters only, 1-5 chars).
        # Use two-letter symbols: AA, AB, …, AZ, BA, …
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        symbols = []
        for i in range(MAX_SYMBOLS_PER_CLIENT):
            symbols.append(alphabet[i // 26] + alphabet[i % 26])
        assert len(symbols) == MAX_SYMBOLS_PER_CLIENT

        await manager.subscribe(client_id, symbols)

        assert len(manager._clients[client_id].subscribed_symbols) == MAX_SYMBOLS_PER_CLIENT

        # One more should be rejected
        ws.send_text.reset_mock()
        extra = await manager.subscribe(client_id, ["ZZZZ"])
        assert "ZZZZ" not in extra
        ws.send_text.assert_called_once()
        payload = json.loads(ws.send_text.call_args[0][0])
        assert payload["code"] == "TOO_MANY_SYMBOLS"

    async def test_on_trade_fans_out_to_subscribers(self):
        from routers.websocket import ConnectionManager
        from services.finnhub_service import FinnhubTradeData

        manager = ConnectionManager()
        manager._ws_manager = self._make_mock_ws_manager()

        ws1 = self._make_mock_websocket()
        ws2 = self._make_mock_websocket()
        cid1 = await manager.connect(ws1)
        cid2 = await manager.connect(ws2)

        await manager.subscribe(cid1, ["AAPL"])
        await manager.subscribe(cid2, ["AAPL"])

        trade = FinnhubTradeData(
            symbol="AAPL",
            price=178.25,
            volume=100.0,
            timestamp=datetime.now(tz=timezone.utc),
        )
        await manager._on_trade(trade)

        # Both clients should receive the trade message
        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()
        payload = json.loads(ws1.send_text.call_args[0][0])
        assert payload["type"] == "trade"
        assert payload["symbol"] == "AAPL"
        assert payload["price"] == 178.25

    async def test_on_trade_does_not_send_to_unsubscribed_client(self):
        from routers.websocket import ConnectionManager
        from services.finnhub_service import FinnhubTradeData

        manager = ConnectionManager()
        manager._ws_manager = self._make_mock_ws_manager()

        ws = self._make_mock_websocket()
        cid = await manager.connect(ws)
        await manager.subscribe(cid, ["MSFT"])  # subscribed to MSFT, not AAPL

        trade = FinnhubTradeData(
            symbol="AAPL",
            price=178.25,
            volume=100.0,
            timestamp=datetime.now(tz=timezone.utc),
        )
        await manager._on_trade(trade)

        # Client should NOT receive an AAPL trade
        ws.send_text.assert_not_called()

    async def test_disconnect_unsubscribes_from_upstream(self):
        from routers.websocket import ConnectionManager

        manager = ConnectionManager()
        ws_mgr = self._make_mock_ws_manager()
        manager._ws_manager = ws_mgr

        ws = self._make_mock_websocket()
        client_id = await manager.connect(ws)
        await manager.subscribe(client_id, ["AAPL"])

        # Disconnecting the only subscriber should unsubscribe upstream
        await manager.disconnect(client_id)
        ws_mgr.unsubscribe.assert_called_once_with("AAPL")

    async def test_startup_connects_upstream(self):
        from routers.websocket import ConnectionManager

        manager = ConnectionManager()
        mock_ws_mgr = self._make_mock_ws_manager()

        # Patch the `settings` name as imported inside the websocket module,
        # not the canonical `config.settings`, so the if-guard sees the key.
        with patch("routers.websocket.get_ws_manager", return_value=mock_ws_mgr):
            with patch("routers.websocket.settings") as mock_settings:
                mock_settings.finnhub_api_key = "test_key"
                mock_settings.ws_max_connections = 100
                mock_settings.ws_ping_interval = 30
                await manager.startup()

        mock_ws_mgr.add_handler.assert_called_once()
        mock_ws_mgr.connect.assert_called_once()

        # Cleanup
        if manager._ping_task:
            manager._ping_task.cancel()
            try:
                await manager._ping_task
            except asyncio.CancelledError:
                pass


# ---------------------------------------------------------------------------
# GET /ws/status endpoint
# ---------------------------------------------------------------------------


class TestWebSocketStatusEndpoint:
    """Integration tests for the GET /ws/status REST endpoint."""

    def test_status_returns_200(self, client: TestClient):
        resp = client.get("/ws/status")
        assert resp.status_code == status.HTTP_200_OK

    def test_status_response_structure(self, client: TestClient):
        resp = client.get("/ws/status")
        data = resp.json()
        assert "connected_clients" in data
        assert "subscribed_symbols" in data
        assert "upstream_connected" in data
        assert "upstream_symbols" in data

    def test_status_initial_state(self, client: TestClient):
        resp = client.get("/ws/status")
        data = resp.json()
        assert isinstance(data["connected_clients"], int)
        assert isinstance(data["subscribed_symbols"], int)
        assert isinstance(data["upstream_connected"], bool)
        assert isinstance(data["upstream_symbols"], int)
