"""
Tests for the Finnhub service (REST API and WebSocket manager).

Coverage:
- FinnhubService.get_quote()           – success, not found, auth error, rate limit
- FinnhubService.get_company_profile() – success, not found
- FinnhubService.get_candles()         – success, no_data, missing fields
- Response parsers                     – edge-cases (zero price, empty dicts, etc.)
- FinnhubWebSocketManager              – connect, disconnect, subscribe, unsubscribe,
                                         handlers, message parsing, reconnection flags
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from models.market import AssetType, CompanyProfile, HistoricalData, OHLCV, Quote
from services.base import (
    AuthenticationError,
    CacheType,
    NotFoundError,
    RateLimitError,
    ServiceError,
)
from services.finnhub_service import (
    FinnhubService,
    FinnhubTradeData,
    FinnhubWebSocketManager,
    get_finnhub_service,
    get_ws_manager,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service():
    """Return a fresh FinnhubService instance."""
    return FinnhubService()


@pytest.fixture
def ws_manager():
    """Return a fresh FinnhubWebSocketManager with a dummy key."""
    return FinnhubWebSocketManager(api_key="test_api_key")


@pytest.fixture
def mock_quote_response():
    """Raw Finnhub /quote response for AAPL."""
    return {
        "c": 178.50,
        "d": 2.35,
        "dp": 1.33,
        "h": 179.20,
        "l": 176.80,
        "o": 177.00,
        "pc": 176.15,
        "t": 1741276800,  # 2026-03-06 16:00:00 UTC
    }


@pytest.fixture
def mock_profile_response():
    """Raw Finnhub /stock/profile2 response for AAPL."""
    return {
        "country": "US",
        "currency": "USD",
        "exchange": "NASDAQ/NMS (Global Select Market)",
        "ipo": "1980-12-12",
        "marketCapitalization": 2800000.0,
        "name": "Apple Inc",
        "phone": "14089961010",
        "shareOutstanding": 15441.88,
        "ticker": "AAPL",
        "weburl": "https://www.apple.com/",
        "logo": "https://static.finnhub.io/logo/test.png",
        "finnhubIndustry": "Technology",
    }


@pytest.fixture
def mock_candle_response():
    """Raw Finnhub /stock/candle response for 3 daily bars."""
    return {
        "s": "ok",
        "c": [150.00, 151.50, 152.75],
        "h": [151.00, 152.00, 153.50],
        "l": [149.00, 150.50, 151.00],
        "o": [149.50, 150.25, 151.75],
        "v": [45000000, 52000000, 48000000],
        "t": [1741132800, 1741219200, 1741305600],
    }


# ---------------------------------------------------------------------------
# FinnhubService — basic configuration
# ---------------------------------------------------------------------------


def test_service_name(service):
    assert service.SERVICE_NAME == "finnhub"


def test_get_base_url(service):
    assert service._get_base_url() == "https://finnhub.io/api/v1"


def test_get_api_key_from_settings(service, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "finnhub_api_key", "my_test_key")
    assert service._get_api_key() == "my_test_key"


def test_resolution_map_covers_common_intervals(service):
    expected = {"1m", "5m", "15m", "30m", "1h", "1d", "1w", "1M"}
    assert expected.issubset(set(service.RESOLUTION_MAP.keys()))


# ---------------------------------------------------------------------------
# FinnhubService.get_quote — success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_quote_returns_quote_model(service, mock_quote_response, monkeypatch):
    """get_quote() should return a populated Quote instance."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_quote_response

    with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp):
        quote = await service.get_quote("aapl")  # lowercase → normalised

    assert isinstance(quote, Quote)
    assert quote.symbol == "AAPL"
    assert quote.asset_type == AssetType.STOCK
    assert quote.price == 178.50
    assert quote.change == 2.35
    assert quote.change_percent == 1.33
    assert quote.high_24h == 179.20
    assert quote.low_24h == 176.80
    assert quote.open_price == 177.00
    assert quote.previous_close == 176.15
    assert quote.source == "finnhub"
    assert isinstance(quote.timestamp, datetime)

    await service.close()


@pytest.mark.asyncio
async def test_get_quote_timestamp_is_utc(service, mock_quote_response, monkeypatch):
    """Timestamp on Quote should be timezone-aware UTC."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_quote_response

    with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp):
        quote = await service.get_quote("AAPL")

    assert quote.timestamp.tzinfo is not None

    await service.close()


@pytest.mark.asyncio
async def test_get_quote_uses_cache_on_second_call(service, mock_quote_response):
    """Second identical call must be served from cache (no HTTP request)."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_quote_response

    with patch.object(
        httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
    ) as mock_req:
        await service.get_quote("AAPL")
        await service.get_quote("AAPL")

    # HTTP client must only be called once
    assert mock_req.call_count == 1

    await service.close()


# ---------------------------------------------------------------------------
# FinnhubService.get_quote — error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_quote_raises_not_found_for_zero_price(service):
    """A zero current price indicates an unknown symbol → NotFoundError."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"c": 0, "d": 0, "dp": 0, "h": 0, "l": 0, "o": 0, "pc": 0, "t": 0}

    with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp):
        with pytest.raises(NotFoundError) as exc_info:
            await service.get_quote("INVALID")

    assert exc_info.value.resource == "INVALID"
    assert exc_info.value.service == "finnhub"

    await service.close()


@pytest.mark.asyncio
async def test_get_quote_raises_not_found_for_empty_response(service):
    """An empty response dict should raise NotFoundError."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {}

    with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp):
        with pytest.raises(NotFoundError):
            await service.get_quote("UNKNOWN")

    await service.close()


@pytest.mark.asyncio
async def test_get_quote_raises_auth_error_on_401(service):
    """HTTP 401 from Finnhub must raise AuthenticationError."""
    mock_resp = MagicMock()
    mock_resp.status_code = 401

    with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp):
        with pytest.raises(AuthenticationError) as exc_info:
            await service.get_quote("AAPL")

    assert exc_info.value.service == "finnhub"

    await service.close()


@pytest.mark.asyncio
async def test_get_quote_raises_rate_limit_on_429(service):
    """HTTP 429 from Finnhub must raise RateLimitError after retries."""
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.headers = {"Retry-After": "30"}

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
        ):
            with pytest.raises(RateLimitError) as exc_info:
                await service.get_quote("AAPL")

    assert exc_info.value.service == "finnhub"
    assert exc_info.value.retry_after == 30

    await service.close()


# ---------------------------------------------------------------------------
# FinnhubService.get_company_profile — success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_company_profile_returns_model(service, mock_profile_response):
    """get_company_profile() should return a CompanyProfile."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_profile_response

    with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp):
        profile = await service.get_company_profile("AAPL")

    assert isinstance(profile, CompanyProfile)
    assert profile.symbol == "AAPL"
    assert profile.name == "Apple Inc"
    assert profile.exchange == "NASDAQ/NMS (Global Select Market)"
    assert profile.country == "US"
    assert profile.currency == "USD"
    assert profile.industry == "Technology"
    assert profile.ipo_date == "1980-12-12"
    assert profile.market_cap == 2800000.0
    assert profile.shares_outstanding == 15441.88
    assert profile.website == "https://www.apple.com/"
    assert profile.logo == "https://static.finnhub.io/logo/test.png"
    assert profile.phone == "14089961010"
    assert profile.source == "finnhub"

    await service.close()


@pytest.mark.asyncio
async def test_get_company_profile_cached(service, mock_profile_response):
    """Profile should be cached (fundamentals TTL) after first fetch."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_profile_response

    with patch.object(
        httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
    ) as mock_req:
        await service.get_company_profile("AAPL")
        await service.get_company_profile("AAPL")

    assert mock_req.call_count == 1

    await service.close()


# ---------------------------------------------------------------------------
# FinnhubService.get_company_profile — error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_company_profile_raises_not_found_for_empty_dict(service):
    """Empty profile dict (Finnhub's way of saying symbol unknown) → NotFoundError."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {}

    with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp):
        with pytest.raises(NotFoundError) as exc_info:
            await service.get_company_profile("FAKE")

    assert exc_info.value.resource == "FAKE"

    await service.close()


@pytest.mark.asyncio
async def test_get_company_profile_raises_not_found_when_ticker_absent(service):
    """Profile dict without 'ticker' field should raise NotFoundError."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    # Response looks populated but has no 'ticker' key
    mock_resp.json.return_value = {"name": "Fake Corp", "exchange": "OTC"}

    with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp):
        with pytest.raises(NotFoundError):
            await service.get_company_profile("FAKE")

    await service.close()


# ---------------------------------------------------------------------------
# FinnhubService.get_candles — success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_candles_returns_historical_data(service, mock_candle_response):
    """get_candles() should return HistoricalData with correctly parsed candles."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_candle_response

    with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp):
        hist = await service.get_candles("AAPL", resolution="D")

    assert isinstance(hist, HistoricalData)
    assert hist.symbol == "AAPL"
    assert hist.asset_type == AssetType.STOCK
    assert hist.source == "finnhub"
    assert len(hist.candles) == 3

    # Verify candle values
    first = hist.candles[0]
    assert isinstance(first, OHLCV)
    assert first.close == 150.00
    assert first.high == 151.00
    assert first.low == 149.00
    assert first.open == 149.50
    assert first.volume == 45000000

    await service.close()


@pytest.mark.asyncio
async def test_get_candles_sorted_chronologically(service, mock_candle_response):
    """Candles must be returned in ascending timestamp order."""
    # Shuffle the timestamps in the response
    shuffled = dict(mock_candle_response)
    shuffled["t"] = [1741305600, 1741132800, 1741219200]
    shuffled["c"] = [152.75, 150.00, 151.50]
    shuffled["h"] = [153.50, 151.00, 152.00]
    shuffled["l"] = [151.00, 149.00, 150.50]
    shuffled["o"] = [151.75, 149.50, 150.25]
    shuffled["v"] = [48000000, 45000000, 52000000]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = shuffled

    with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp):
        hist = await service.get_candles("AAPL")

    timestamps = [c.timestamp for c in hist.candles]
    assert timestamps == sorted(timestamps)

    await service.close()


@pytest.mark.asyncio
async def test_get_candles_resolution_alias_mapping(service, mock_candle_response):
    """Human-friendly resolution aliases (e.g. '1h') should be converted."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_candle_response

    with patch.object(
        httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp
    ) as mock_req:
        await service.get_candles("AAPL", resolution="1h")

    # The params sent to Finnhub should use "60" not "1h"
    call_kwargs = mock_req.call_args
    params = call_kwargs.kwargs.get("params") or call_kwargs.args[2] if call_kwargs.args else {}
    # Extract from keyword args
    if call_kwargs.kwargs:
        params = call_kwargs.kwargs.get("params", {})
    assert params.get("resolution") == "60"

    await service.close()


# ---------------------------------------------------------------------------
# FinnhubService.get_candles — error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_candles_raises_not_found_for_no_data_status(service):
    """Finnhub 'no_data' status should raise NotFoundError."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"s": "no_data"}

    with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp):
        with pytest.raises(NotFoundError) as exc_info:
            await service.get_candles("AAPL")

    assert "no historical candle data" in str(exc_info.value).lower()

    await service.close()


@pytest.mark.asyncio
async def test_get_candles_raises_service_error_for_missing_field(service):
    """Missing required array (e.g. 'v') should raise ServiceError."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "s": "ok",
        "c": [150.0],
        "h": [151.0],
        "l": [149.0],
        "o": [149.5],
        # 'v' is missing
        "t": [1741132800],
    }

    with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp):
        with pytest.raises(ServiceError):
            await service.get_candles("AAPL")

    await service.close()


@pytest.mark.asyncio
async def test_get_candles_raises_service_error_for_mismatched_arrays(service):
    """Arrays of different lengths should raise ServiceError."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "s": "ok",
        "c": [150.0, 151.0],   # 2 items
        "h": [151.0],           # 1 item — mismatch
        "l": [149.0, 150.0],
        "o": [149.5, 150.0],
        "v": [45000000, 52000000],
        "t": [1741132800, 1741219200],
    }

    with patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock, return_value=mock_resp):
        with pytest.raises(ServiceError) as exc_info:
            await service.get_candles("AAPL")

    assert "mismatch" in str(exc_info.value).lower()

    await service.close()


# ---------------------------------------------------------------------------
# _parse_quote — unit tests (no HTTP)
# ---------------------------------------------------------------------------


def test_parse_quote_uses_fallback_timestamp_when_missing(service):
    """If 't' is missing, timestamp should default to now (UTC)."""
    data = {"c": 100.0, "d": 1.0, "dp": 1.0, "h": 101.0, "l": 99.0, "o": 99.5, "pc": 99.0}
    quote = service._parse_quote("TEST", data)
    assert quote.timestamp.tzinfo is not None


def test_parse_quote_handles_none_optional_fields(service):
    """Optional fields with None/0 values should be stored as None."""
    data = {
        "c": 50.0,
        "d": None,
        "dp": None,
        "h": None,
        "l": None,
        "o": None,
        "pc": None,
        "t": 0,
    }
    quote = service._parse_quote("TEST", data)
    assert quote.price == 50.0
    assert quote.change == 0.0
    assert quote.change_percent == 0.0
    assert quote.high_24h is None
    assert quote.low_24h is None


def test_parse_candles_reverses_to_chronological(service):
    """_parse_candles should sort candles by ascending timestamp."""
    data = {
        "s": "ok",
        "t": [1741305600, 1741219200, 1741132800],
        "o": [151.75, 150.25, 149.50],
        "h": [153.50, 152.00, 151.00],
        "l": [151.00, 150.50, 149.00],
        "c": [152.75, 151.50, 150.00],
        "v": [48000000.0, 52000000.0, 45000000.0],
    }
    hist = service._parse_candles("AAPL", "D", data)
    ts_list = [c.timestamp.timestamp() for c in hist.candles]
    assert ts_list == sorted(ts_list)


# ---------------------------------------------------------------------------
# FinnhubWebSocketManager — configuration & state
# ---------------------------------------------------------------------------


def test_ws_manager_initial_state(ws_manager):
    assert not ws_manager.is_connected
    assert ws_manager.subscribed_symbols == set()
    assert ws_manager._running is False
    assert ws_manager._task is None


def test_ws_manager_ws_url_template(ws_manager):
    url = ws_manager.WS_URL_TEMPLATE.format(token="MY_KEY")
    assert url == "wss://ws.finnhub.io?token=MY_KEY"


# ---------------------------------------------------------------------------
# FinnhubWebSocketManager — handler registration
# ---------------------------------------------------------------------------


def test_add_handler(ws_manager):
    async def my_handler(trade):
        pass

    ws_manager.add_handler(my_handler)
    assert my_handler in ws_manager._handlers


def test_add_handler_idempotent(ws_manager):
    """Adding the same handler twice should not duplicate it."""

    async def my_handler(trade):
        pass

    ws_manager.add_handler(my_handler)
    ws_manager.add_handler(my_handler)
    assert ws_manager._handlers.count(my_handler) == 1


def test_remove_handler(ws_manager):
    async def my_handler(trade):
        pass

    ws_manager.add_handler(my_handler)
    ws_manager.remove_handler(my_handler)
    assert my_handler not in ws_manager._handlers


def test_remove_nonexistent_handler_is_noop(ws_manager):
    """Removing a handler that was never added should not raise."""

    async def phantom(trade):
        pass

    ws_manager.remove_handler(phantom)  # should not raise


# ---------------------------------------------------------------------------
# FinnhubWebSocketManager — subscribe / unsubscribe (no live connection)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscribe_adds_to_tracked_symbols(ws_manager):
    await ws_manager.subscribe("AAPL")
    assert "AAPL" in ws_manager.subscribed_symbols


@pytest.mark.asyncio
async def test_subscribe_normalises_symbol_case(ws_manager):
    await ws_manager.subscribe("msft")
    assert "MSFT" in ws_manager.subscribed_symbols
    assert "msft" not in ws_manager.subscribed_symbols


@pytest.mark.asyncio
async def test_unsubscribe_removes_from_tracked_symbols(ws_manager):
    await ws_manager.subscribe("GOOG")
    await ws_manager.unsubscribe("GOOG")
    assert "GOOG" not in ws_manager.subscribed_symbols


@pytest.mark.asyncio
async def test_unsubscribe_nonexistent_symbol_is_noop(ws_manager):
    """Unsubscribing from a symbol that was never subscribed should not raise."""
    await ws_manager.unsubscribe("NOPE")  # should not raise


# ---------------------------------------------------------------------------
# FinnhubWebSocketManager — _parse_trade
# ---------------------------------------------------------------------------


def test_parse_trade_valid(ws_manager):
    raw = {"s": "AAPL", "p": 178.5, "t": 1741276800000, "v": 100.0, "c": ["1"]}
    trade = ws_manager._parse_trade(raw)

    assert trade is not None
    assert trade.symbol == "AAPL"
    assert trade.price == 178.5
    assert trade.volume == 100.0
    assert trade.conditions == ["1"]
    assert trade.timestamp.tzinfo is not None
    # Timestamp should be ms → seconds
    expected_ts = datetime.fromtimestamp(1741276800000 / 1000.0, tz=timezone.utc)
    assert trade.timestamp == expected_ts


def test_parse_trade_missing_required_field_returns_none(ws_manager):
    """Missing 'p' (price) should return None instead of raising."""
    raw = {"s": "AAPL", "t": 1741276800000, "v": 100.0}
    result = ws_manager._parse_trade(raw)
    assert result is None


def test_parse_trade_missing_symbol_returns_none(ws_manager):
    raw = {"p": 100.0, "t": 1741276800000, "v": 50.0}
    result = ws_manager._parse_trade(raw)
    assert result is None


def test_parse_trade_invalid_price_type_returns_none(ws_manager):
    raw = {"s": "AAPL", "p": "not-a-number", "t": 1741276800000, "v": 100.0}
    result = ws_manager._parse_trade(raw)
    assert result is None


def test_parse_trade_optional_conditions_defaults_to_none(ws_manager):
    raw = {"s": "TSLA", "p": 250.0, "t": 1741276800000, "v": 200.0}
    trade = ws_manager._parse_trade(raw)
    assert trade is not None
    assert trade.conditions is None


# ---------------------------------------------------------------------------
# FinnhubWebSocketManager — _handle_message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_message_dispatches_trade_data(ws_manager):
    """Trade message should call all registered handlers with FinnhubTradeData."""
    received: List[FinnhubTradeData] = []

    async def capture(trade: FinnhubTradeData):
        received.append(trade)

    ws_manager.add_handler(capture)

    trade_msg = json.dumps({
        "type": "trade",
        "data": [
            {"s": "AAPL", "p": 178.5, "t": 1741276800000, "v": 100.0},
            {"s": "MSFT", "p": 420.0, "t": 1741276800000, "v": 50.0},
        ],
    })

    await ws_manager._handle_message(trade_msg)

    # Give the asyncio tasks a chance to run
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert len(received) == 2
    symbols = {t.symbol for t in received}
    assert symbols == {"AAPL", "MSFT"}


@pytest.mark.asyncio
async def test_handle_message_ignores_invalid_json(ws_manager):
    """Invalid JSON should be ignored without raising."""
    await ws_manager._handle_message("this is not json {}")


@pytest.mark.asyncio
async def test_handle_message_unknown_type_is_noop(ws_manager):
    """Unknown message types should be silently ignored."""
    msg = json.dumps({"type": "news", "data": "some data"})
    await ws_manager._handle_message(msg)  # should not raise


@pytest.mark.asyncio
async def test_handle_message_skips_unparseable_trade(ws_manager):
    """Trade entries that fail to parse should be skipped; valid ones dispatched."""
    received: List[FinnhubTradeData] = []

    async def capture(trade: FinnhubTradeData):
        received.append(trade)

    ws_manager.add_handler(capture)

    trade_msg = json.dumps({
        "type": "trade",
        "data": [
            {"s": "AAPL", "p": 178.5, "t": 1741276800000, "v": 100.0},  # valid
            {"s": "BAD", "t": 1741276800000, "v": 10.0},                  # missing 'p'
        ],
    })

    await ws_manager._handle_message(trade_msg)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert len(received) == 1
    assert received[0].symbol == "AAPL"


# ---------------------------------------------------------------------------
# FinnhubWebSocketManager — connect / disconnect lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_starts_background_task(ws_manager):
    """connect() should set _running=True and create a background task."""
    with patch.object(ws_manager, "_run", new_callable=AsyncMock):
        await ws_manager.connect()

    assert ws_manager._running is True
    assert ws_manager._task is not None

    # Cleanup
    ws_manager._running = False
    ws_manager._task.cancel()
    try:
        await ws_manager._task
    except (asyncio.CancelledError, Exception):
        pass


@pytest.mark.asyncio
async def test_connect_is_idempotent(ws_manager):
    """Calling connect() twice should not create a second task."""
    with patch.object(ws_manager, "_run", new_callable=AsyncMock):
        await ws_manager.connect()
        first_task = ws_manager._task
        await ws_manager.connect()  # second call

    assert ws_manager._task is first_task  # same task, not replaced

    # Cleanup
    ws_manager._running = False
    first_task.cancel()
    try:
        await first_task
    except (asyncio.CancelledError, Exception):
        pass


@pytest.mark.asyncio
async def test_disconnect_stops_running_flag(ws_manager):
    """disconnect() should set _running=False."""
    with patch.object(ws_manager, "_run", new_callable=AsyncMock):
        await ws_manager.connect()

    await ws_manager.disconnect()
    assert ws_manager._running is False


@pytest.mark.asyncio
async def test_disconnect_closes_websocket(ws_manager):
    """disconnect() should close an open WebSocket."""
    mock_ws = AsyncMock()
    mock_ws.closed = False
    ws_manager._ws = mock_ws
    ws_manager._running = True

    await ws_manager.disconnect()

    mock_ws.close.assert_called_once()


# ---------------------------------------------------------------------------
# FinnhubWebSocketManager — _run reconnection logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_resubscribes_on_reconnect(ws_manager):
    """After reconnection, _run should send subscribe messages for all symbols."""
    ws_manager._subscribed_symbols = {"AAPL", "MSFT"}

    sent_messages = []

    class FakeWS:
        closed = False

        async def send(self, msg):
            sent_messages.append(json.loads(msg))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def __aiter__(self):
            # Yield nothing — connection drops immediately
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    with patch("websockets.connect", return_value=FakeWS()):
        # Run for one connection cycle then stop
        ws_manager._running = True
        # Patch asyncio.sleep to stop the loop after first attempt
        sleep_calls = []

        async def fake_sleep(seconds):
            sleep_calls.append(seconds)
            ws_manager._running = False  # Stop after first reconnect sleep

        with patch("asyncio.sleep", side_effect=fake_sleep):
            await ws_manager._run()

    # All subscribed symbols should have received a subscribe message
    subscribe_types = [m["type"] for m in sent_messages]
    subscribe_syms = {m["symbol"] for m in sent_messages if m["type"] == "subscribe"}
    assert "subscribe" in subscribe_types
    assert subscribe_syms == {"AAPL", "MSFT"}


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------


def test_get_finnhub_service_returns_instance():
    import services.finnhub_service as mod

    # Reset singleton
    mod._finnhub_service = None
    svc = get_finnhub_service()
    assert isinstance(svc, FinnhubService)


def test_get_finnhub_service_singleton():
    """get_finnhub_service() should return the same instance on repeated calls."""
    import services.finnhub_service as mod

    mod._finnhub_service = None
    s1 = get_finnhub_service()
    s2 = get_finnhub_service()
    assert s1 is s2


def test_get_ws_manager_returns_instance(monkeypatch):
    import services.finnhub_service as mod

    mod._ws_manager = None
    from config import settings

    monkeypatch.setattr(settings, "finnhub_api_key", "test_ws_key")

    mgr = get_ws_manager()
    assert isinstance(mgr, FinnhubWebSocketManager)
    assert mgr._api_key == "test_ws_key"


def test_get_ws_manager_singleton(monkeypatch):
    import services.finnhub_service as mod

    mod._ws_manager = None
    from config import settings

    monkeypatch.setattr(settings, "finnhub_api_key", "test_ws_key_2")

    m1 = get_ws_manager()
    m2 = get_ws_manager()
    assert m1 is m2
