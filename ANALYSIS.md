# Market Monitor - Codebase Analysis & Missing Functionality

**Analysis Date:** March 6, 2026  
**Priority:** Medium  
**Status:** Foundation Complete, Core Features Missing

---

## Executive Summary

The Market Monitor project has a **solid foundation** with excellent architecture, testing infrastructure, and documentation. However, **all core business functionality is missing**. The project is currently at **~15% completion** with infrastructure in place but no data integration or user-facing features implemented.

### What's Complete ✅
- Backend infrastructure (FastAPI, routing, middleware)
- Multi-tier caching system (CacheManager)
- Rate limiting system (RateLimiter)
- Structured logging
- Health check endpoints
- Comprehensive test suite (pytest + pytest-asyncio)
- Pydantic v2 data models
- CORS configuration
- Error handling
- Documentation (README, API docs, deployment guides)

### What's Missing ❌
- **All external API integrations** (Finnhub, CoinGecko, yfinance, FMP)
- **All data endpoints** (quotes, historical, screener)
- **WebSocket real-time feeds**
- **Frontend UI** (still default Vite template)
- **Frontend state management**
- **Charts and visualizations**

---

## 1. Relevant Files and Modules

### Backend Structure

```
backend/
├── Core Application ✅ IMPLEMENTED
│   ├── main.py                  # FastAPI app, middleware, exception handlers
│   ├── config.py               # Environment-based settings
│   └── routers/
│       └── health.py           # Health check endpoints (3 endpoints)
│
├── Data Models ✅ IMPLEMENTED BUT UNUSED
│   ├── models/base.py          # HealthCheck, ErrorResponse, SuccessResponse
│   └── models/market.py        # Quote, OHLCV, HistoricalData, AssetType
│
├── Utilities ✅ IMPLEMENTED
│   ├── utils/cache.py          # CacheManager with 3 TTL tiers
│   ├── utils/rate_limiter.py   # RateLimiter with sliding window
│   └── utils/logger.py         # Structured logging setup
│
├── Services ❌ MISSING (CRITICAL)
│   └── services/__init__.py    # Empty placeholder
│       # MISSING: finnhub_service.py
│       # MISSING: coingecko_service.py
│       # MISSING: yfinance_service.py
│       # MISSING: fmp_service.py
│
└── Tests ✅ IMPLEMENTED
    ├── tests/test_health_endpoints.py  # 15 integration tests
    ├── tests/test_cache_manager.py     # Unit tests for caching
    ├── tests/test_rate_limiter.py      # Unit tests for rate limiting
    └── tests/test_models.py            # Model validation tests
```

### Frontend Structure

```
frontend/
├── src/
│   ├── App.tsx              ❌ Default Vite template (not customized)
│   ├── main.tsx            ✅ Basic setup complete
│   └── test/
│       └── setup.ts        ✅ Vitest config
│
├── Public Assets           ✅ Default Vite assets
│
└── Configuration           ✅ Complete
    ├── vite.config.ts      # Vite + React setup
    ├── tailwind.config.js  # TailwindCSS 4
    └── tsconfig.json       # TypeScript config
```

---

## 2. Existing Patterns and Conventions

### Backend Patterns ✅

#### 1. **Service Layer Architecture** (Defined but not implemented)
```python
# Expected pattern from services/__init__.py:
from .finnhub_service import FinnhubService
from .coingecko_service import CoinGeckoService

# Each service should follow the pattern:
class BaseService:
    async def get_quote(symbol: str) -> Quote
    async def get_historical(symbol: str, interval: str) -> HistoricalData
    # Includes fallback logic and error handling
```

#### 2. **Caching Pattern** (Implemented)
```python
# utils/cache.py
# Three-tier caching with different TTLs:
- quotes_cache: 60s (real-time data)
- historical_cache: 3600s (daily candles)
- fundamentals_cache: 86400s (company data)

# Usage pattern:
cache_key = f"{symbol}"
if cache_key in cache_manager.quotes_cache:
    return cache_manager.quotes_cache[cache_key]
```

#### 3. **Rate Limiting Pattern** (Implemented)
```python
# utils/rate_limiter.py
# Sliding window rate limiter per service:
if rate_limiter.can_call("finnhub"):
    response = await service.call_api()
    rate_limiter.record_call("finnhub")
else:
    # Use fallback service
```

#### 4. **Error Handling Pattern** (Implemented)
```python
# Standardized error responses via ErrorResponse model
# Global exception handlers in main.py
# Structured logging with contextual data
```

#### 5. **Model Validation Pattern** (Implemented)
```python
# Pydantic v2 models with Field validators
# JSON schema examples for API documentation
# Type hints throughout
```

### Frontend Patterns ❌ (Not yet established)

Expected patterns based on README:
- Zustand for state management (not installed)
- Recharts or Lightweight Charts (not installed)
- Component-based architecture (not implemented)

---

## 3. Dependencies and Integration Points

### External API Dependencies (All Missing)

#### 1. **Finnhub Service** ❌ MISSING
```python
# backend/services/finnhub_service.py (DOES NOT EXIST)
class FinnhubService:
    """
    Primary stock data provider.
    - REST API: /quote endpoint for real-time quotes
    - WebSocket: Real-time US stock quotes
    - Company news and fundamentals
    
    Free tier: 60 calls/min
    Fallback: yfinance -> FMP
    """
    
    async def get_quote(self, symbol: str) -> Quote:
        """Fetch real-time stock quote."""
        pass  # NOT IMPLEMENTED
    
    async def get_historical(self, symbol: str, interval: str) -> HistoricalData:
        """Fetch historical OHLCV data."""
        pass  # NOT IMPLEMENTED
```

**Integration Points:**
- config.py: `FINNHUB_API_KEY` environment variable ✅
- utils/cache.py: `quotes_cache` for 60s caching ✅
- utils/rate_limiter.py: Rate limit tracking ✅
- routers/quotes.py: Quote endpoint ❌ (router doesn't exist)

---

#### 2. **CoinGecko Service** ❌ MISSING
```python
# backend/services/coingecko_service.py (DOES NOT EXIST)
class CoinGeckoService:
    """
    Primary crypto data provider.
    - /simple/price: Current prices
    - /coins/{id}/market_chart: Historical data
    - /coins/markets: Market data with rankings
    
    Free tier: 30-50 calls/min, 10k/month
    Fallback: Binance public API (via CCXT)
    """
    
    async def get_quote(self, symbol: str) -> Quote:
        """Fetch real-time crypto quote."""
        pass  # NOT IMPLEMENTED
```

**Integration Points:**
- config.py: `COINGECKO_API_KEY` environment variable ✅
- utils/cache.py: `quotes_cache` for 60s caching ✅
- models/market.py: `AssetType.CRYPTO` ✅

---

#### 3. **yfinance Service** ❌ MISSING
```python
# backend/services/yfinance_service.py (DOES NOT EXIST)
class YFinanceService:
    """
    Fallback for historical stock data.
    - No API key required (scrapes Yahoo Finance)
    - Adjusted for splits and dividends
    - WARNING: Unofficial, can break
    
    Free tier: Unlimited (but unstable)
    Fallback for: Finnhub historical data
    """
    
    async def get_historical(self, symbol: str, period: str) -> HistoricalData:
        """Fetch historical data from Yahoo Finance."""
        pass  # NOT IMPLEMENTED
```

**Integration Points:**
- requirements.txt: `yfinance` installed ✅
- Used as fallback when Finnhub fails ❌ (no fallback logic implemented)

---

#### 4. **FMP Service** ❌ MISSING
```python
# backend/services/fmp_service.py (DOES NOT EXIST)
class FMPService:
    """
    Financial fundamentals provider.
    - /quote endpoint: Stock quotes
    - /profile endpoint: Company fundamentals
    - /historical-price-full: Historical data
    
    Free tier: 250 calls/day (very limited)
    Use cases: Fundamentals, fallback quotes
    """
    
    async def get_fundamentals(self, symbol: str) -> dict:
        """Fetch company fundamentals."""
        pass  # NOT IMPLEMENTED
```

**Integration Points:**
- config.py: `FMP_API_KEY` environment variable ✅
- utils/cache.py: `fundamentals_cache` for 24h caching ✅

---

### Missing API Routers

#### 1. **Quotes Router** ❌ MISSING
```python
# backend/routers/quotes.py (DOES NOT EXIST)
"""
Expected endpoints:
- GET /api/quotes/{symbol}         # Single quote
- GET /api/quotes/batch            # Multiple quotes
- Query params: ?source=finnhub    # Force specific provider
"""
```

#### 2. **Historical Router** ❌ MISSING
```python
# backend/routers/historical.py (DOES NOT EXIST)
"""
Expected endpoints:
- GET /api/historical/{symbol}
- Query params: ?interval=1d&from=2024-01-01&to=2024-12-31
"""
```

#### 3. **Screener Router** ❌ MISSING
```python
# backend/routers/screener.py (DOES NOT EXIST)
"""
Expected endpoints:
- GET /api/screener               # Basic screening
- POST /api/screener/technical    # With indicators (RSI, MACD, SMA)
"""
```

#### 4. **WebSocket Router** ❌ MISSING
```python
# backend/routers/websocket.py (DOES NOT EXIST)
"""
Expected endpoints:
- WS /ws/quotes                   # Real-time price feeds
"""
```

---

### Missing Frontend Components

#### 1. **State Management** ❌ MISSING
```typescript
// frontend/src/store/ (DOES NOT EXIST)
// Expected: Zustand stores for:
// - watchlistStore.ts
// - quotesStore.ts
// - chartStore.ts
```

#### 2. **API Client** ❌ MISSING
```typescript
// frontend/src/api/ (DOES NOT EXIST)
// Expected: API client with fetch wrappers
// - client.ts
// - quotes.ts
// - historical.ts
```

#### 3. **UI Components** ❌ MISSING
```typescript
// frontend/src/components/ (DOES NOT EXIST)
// Expected components:
// - Dashboard.tsx
// - Watchlist.tsx
// - QuoteCard.tsx
// - CandlestickChart.tsx
// - Screener.tsx
```

---

## 4. Potential Challenges

### High Priority Challenges ⚠️

#### 1. **API Rate Limit Management** (Complex)
**Challenge:** Staying within free-tier quotas across 4+ providers  
**Complexity:** Medium-High  
**Mitigations in place:**
- ✅ Rate limiter implemented (`utils/rate_limiter.py`)
- ✅ Multi-tier caching reduces API calls
- ❌ No actual API call tracking yet (nothing to track)

**Remaining Work:**
- Implement fallback chain: Finnhub → yfinance → FMP
- Add exponential backoff on 429 errors
- Track daily/monthly quotas (not just per-minute)
- Add queue system for non-urgent requests

---

#### 2. **yfinance Reliability** (Known Issue)
**Challenge:** yfinance scrapes Yahoo Finance HTML, which breaks frequently  
**Complexity:** High (external dependency)  
**Documentation Warning:**
> "yfinance can break when Yahoo changes HTML. Not an official API."

**Mitigations:**
- ✅ Use as fallback only (not primary)
- ✅ Aggressive caching (1h TTL for historical data)
- ❌ No actual error handling yet

**Recommended Approach:**
```python
try:
    data = await yfinance_service.get_historical(symbol)
except Exception as e:
    logger.error("yfinance_failed", symbol=symbol, error=str(e))
    # Fall back to FMP or return cached data
    data = await fmp_service.get_historical(symbol)
```

---

#### 3. **WebSocket Connection Management** (Complex)
**Challenge:** Maintain stable WebSocket connections to Finnhub  
**Complexity:** Medium-High  

**Requirements:**
- Finnhub limits: 1 WebSocket connection per API key
- Backend must multiplex: 1 Finnhub WS → N frontend clients
- Handle reconnection with exponential backoff
- Subscribe/unsubscribe to symbols dynamically

**Current State:**
- ❌ No WebSocket server implemented
- ❌ No connection pooling
- ❌ No reconnection logic

**Implementation Needed:**
```python
# backend/services/websocket_manager.py (DOES NOT EXIST)
class WebSocketManager:
    """
    Manages single Finnhub WebSocket connection.
    Broadcasts to multiple FastAPI WebSocket clients.
    """
    async def subscribe(self, symbol: str)
    async def unsubscribe(self, symbol: str)
    async def broadcast_quote(self, quote: Quote)
```

---

#### 4. **Data Model Mismatch** (Medium)
**Challenge:** Different APIs return different data structures  

**Examples:**
- Finnhub: `{"c": 150.25, "pc": 148.00}` (c=current, pc=previous close)
- CoinGecko: `{"usd": 42000, "usd_24h_change": 2.5}`
- yfinance: Returns Pandas DataFrame with OHLCV

**Current State:**
- ✅ Unified `Quote` and `OHLCV` Pydantic models defined
- ❌ No transformation logic to map API responses to models

**Implementation Needed:**
```python
# backend/services/transformers.py (DOES NOT EXIST)
def finnhub_to_quote(response: dict) -> Quote:
    """Transform Finnhub response to Quote model."""
    
def coingecko_to_quote(response: dict) -> Quote:
    """Transform CoinGecko response to Quote model."""
```

---

#### 5. **Crypto vs Stock Symbol Resolution** (Medium)
**Challenge:** Determine if "BTC" is stock or crypto  

**Examples of Ambiguity:**
- "BTC" could be Bitcoin (crypto) or Bolivian Time Corp (stock)
- Need to route to correct API (Finnhub vs CoinGecko)

**Possible Solutions:**
1. **Explicit asset_type parameter** (recommended)
   ```
   GET /api/quotes/BTC?asset_type=crypto
   ```

2. **Symbol prefix convention**
   ```
   CRYPTO:BTC → CoinGecko
   STOCK:AAPL → Finnhub
   ```

3. **Smart detection** (try both, use first success)
   ```python
   try:
       return await finnhub_service.get_quote(symbol)
   except NotFound:
       return await coingecko_service.get_quote(symbol)
   ```

**Current State:**
- ✅ `AssetType` enum defined
- ❌ No routing logic implemented

---

### Medium Priority Challenges ⚠️

#### 6. **Frontend State Synchronization**
**Challenge:** Keep frontend in sync with WebSocket updates  
**Complexity:** Medium  

**Requirements:**
- Update quote cards in real-time
- Update charts without flickering
- Handle WebSocket reconnection gracefully

**Missing Dependencies:**
- Zustand (state management) - not installed
- WebSocket client logic

---

#### 7. **Chart Performance**
**Challenge:** Render thousands of candles without lag  
**Complexity:** Medium  

**Options:**
1. **Recharts** (easier, less performant)
   - Max ~1000 candles before lag
   - Good for daily/weekly data

2. **Lightweight Charts** (recommended for intraday)
   - Can handle 10k+ candles
   - TradingView-style charts
   - More complex API

**Current State:**
- Neither library installed
- No chart components implemented

---

#### 8. **Testing External APIs**
**Challenge:** Write tests without hitting real APIs  
**Complexity:** Low-Medium  

**Required:**
- Mock HTTP responses from Finnhub, CoinGecko, etc.
- Test fallback chains
- Test rate limiting under load

**Current State:**
- ✅ pytest + httpx + pytest-mock installed
- ✅ Test fixtures defined (`conftest.py`)
- ❌ No service tests (no services to test)

**Example Needed:**
```python
@pytest.mark.asyncio
async def test_finnhub_fallback_to_yfinance(mocker):
    """Test fallback when Finnhub fails."""
    mock_finnhub = mocker.patch("services.finnhub.get_quote")
    mock_finnhub.side_effect = Exception("API error")
    
    mock_yfinance = mocker.patch("services.yfinance.get_quote")
    mock_yfinance.return_value = Quote(...)
    
    quote = await get_quote_with_fallback("AAPL")
    assert quote.source == "yfinance"
```

---

### Low Priority Challenges ℹ️

#### 9. **In-Memory Cache Persistence**
**Challenge:** Cache is lost on server restart  
**Impact:** Low (TTLs are short anyway)  
**Future Enhancement:** Migrate to Redis for distributed caching

#### 10. **No User Authentication**
**Challenge:** API is public  
**Impact:** Low (personal project)  
**Future Enhancement:** Add JWT tokens for multi-user support

---

## 5. Implementation Roadmap

### Phase 1: Core Data Integration (v0.2.0) 🚀 **HIGHEST PRIORITY**

**Goal:** Make the app functional with real data

**Tasks:**
1. **Implement Finnhub Service** (2-3 days)
   - `backend/services/finnhub_service.py`
   - `get_quote()` method with caching
   - `get_historical()` method
   - Rate limiting integration
   - Error handling

2. **Implement CoinGecko Service** (2 days)
   - `backend/services/coingecko_service.py`
   - `get_quote()` for crypto
   - `get_historical()` for crypto candles
   - Rate limiting integration

3. **Implement yfinance Service** (1 day)
   - `backend/services/yfinance_service.py`
   - Fallback logic for Finnhub failures
   - Error handling for HTML parsing failures

4. **Create Quotes Router** (1-2 days)
   - `backend/routers/quotes.py`
   - `GET /api/quotes/{symbol}`
   - `GET /api/quotes/batch`
   - Integrate all services with fallback chain
   - Add tests

5. **Testing** (2 days)
   - Unit tests for each service
   - Integration tests for fallback chains
   - Mock API responses

**Deliverable:** Working `/api/quotes/AAPL` endpoint returning real data

---

### Phase 2: Historical Data (v0.3.0)

**Tasks:**
1. **Historical Router** (2 days)
   - `GET /api/historical/{symbol}`
   - Support 1d, 1h, 15m intervals
   - Date range filtering

2. **Historical Data Services** (2 days)
   - Implement in Finnhub, CoinGecko, yfinance services
   - Add historical cache integration (1h TTL)

**Deliverable:** Working historical data endpoint with caching

---

### Phase 3: Frontend Dashboard (v0.4.0)

**Tasks:**
1. **Install Dependencies** (30 mins)
   ```bash
   npm install zustand recharts axios
   ```

2. **Create API Client** (1 day)
   - `frontend/src/api/client.ts`
   - Axios wrapper with error handling

3. **State Management** (1 day)
   - `frontend/src/store/quotesStore.ts`
   - `frontend/src/store/watchlistStore.ts`

4. **UI Components** (3-4 days)
   - Dashboard layout
   - Watchlist component
   - Quote cards with live updates
   - Add/remove symbols

**Deliverable:** Functional dashboard with real quotes

---

### Phase 4: Charts (v0.5.0)

**Tasks:**
1. **Chart Component** (2-3 days)
   - Candlestick chart with Recharts or Lightweight Charts
   - Fetch historical data from API
   - Interactive zoom/pan

2. **Multiple Timeframes** (1 day)
   - 1d, 1h, 15m selector
   - Update chart on interval change

**Deliverable:** Interactive candlestick charts

---

### Phase 5: WebSocket (v0.6.0)

**Tasks:**
1. **WebSocket Manager** (2 days)
   - `backend/services/websocket_manager.py`
   - Manage Finnhub WebSocket connection
   - Multiplex to multiple clients

2. **WebSocket Router** (1 day)
   - `backend/routers/websocket.py`
   - Subscribe/unsubscribe logic

3. **Frontend WebSocket Client** (2 days)
   - Connect to backend WebSocket
   - Update quotes in real-time
   - Handle reconnection

**Deliverable:** Real-time quote updates

---

### Phase 6: Screener (v0.7.0)

**Tasks:**
1. **Screener Router** (2-3 days)
   - `GET /api/screener`
   - `POST /api/screener/technical`
   - Implement RSI, MACD, SMA indicators

2. **Screener UI** (2-3 days)
   - Filter form
   - Results table
   - Technical indicator configuration

**Deliverable:** Working stock/crypto screener

---

## 6. Quick Wins 🎯

### Immediate Tasks (Can complete in 1-2 hours each)

1. **Add Type Stubs for yfinance** ✅
   ```bash
   pip install types-yfinance
   ```

2. **Create Service Base Class** ✅
   ```python
   # backend/services/base.py
   class BaseDataService:
       async def get_quote(self, symbol: str) -> Quote:
           raise NotImplementedError
   ```

3. **Add Finnhub Client Stub** ✅
   ```python
   # backend/services/finnhub_service.py
   class FinnhubService(BaseDataService):
       def __init__(self, api_key: str):
           self.api_key = api_key
           self.base_url = "https://finnhub.io/api/v1"
       
       async def get_quote(self, symbol: str) -> Quote:
           # TODO: Implement
           pass
   ```

4. **Update Frontend App.tsx** ✅
   ```typescript
   // Replace default Vite template with "Market Monitor" title
   ```

---

## 7. Testing Strategy

### Current Test Coverage ✅
- ✅ Health endpoints (15 tests)
- ✅ Cache manager (unit tests)
- ✅ Rate limiter (unit tests)
- ✅ Pydantic models (validation tests)

### Missing Test Coverage ❌
- ❌ Service layer tests (no services yet)
- ❌ Integration tests for data endpoints
- ❌ WebSocket tests
- ❌ Frontend component tests (except default App test)

### Recommended Testing Approach

**For Each Service:**
```python
# Example: tests/test_finnhub_service.py
@pytest.mark.asyncio
async def test_get_quote_success(mocker):
    """Test successful quote fetch."""
    mock_response = {"c": 150.25, "pc": 148.00, "h": 151.00, "l": 147.50}
    mocker.patch("httpx.AsyncClient.get", return_value=mock_response)
    
    service = FinnhubService(api_key="test_key")
    quote = await service.get_quote("AAPL")
    
    assert quote.symbol == "AAPL"
    assert quote.price == 150.25
    assert quote.source == "finnhub"

@pytest.mark.asyncio
async def test_get_quote_fallback_on_error(mocker):
    """Test fallback to yfinance when Finnhub fails."""
    # Mock Finnhub failure
    # Mock yfinance success
    # Assert yfinance was called
```

---

## 8. Critical Missing Files

### Backend (Priority Order)

1. **`backend/services/base.py`** ❌
   - Base class for all data services
   - Defines common interface

2. **`backend/services/finnhub_service.py`** ❌ **CRITICAL**
   - Primary stock data provider
   - Most important service to implement first

3. **`backend/services/coingecko_service.py`** ❌ **CRITICAL**
   - Primary crypto data provider

4. **`backend/services/yfinance_service.py`** ❌ **HIGH**
   - Fallback for historical data

5. **`backend/routers/quotes.py`** ❌ **CRITICAL**
   - Quote endpoints (single + batch)

6. **`backend/routers/historical.py`** ❌ **HIGH**
   - Historical data endpoint

7. **`backend/services/websocket_manager.py`** ❌ **MEDIUM**
   - Manage Finnhub WebSocket connection

8. **`backend/routers/websocket.py`** ❌ **MEDIUM**
   - WebSocket endpoint for frontend

### Frontend (Priority Order)

1. **`frontend/src/api/client.ts`** ❌ **CRITICAL**
   - API client with fetch/axios

2. **`frontend/src/store/quotesStore.ts`** ❌ **CRITICAL**
   - Zustand store for quotes

3. **`frontend/src/components/Dashboard.tsx`** ❌ **HIGH**
   - Main dashboard layout

4. **`frontend/src/components/Watchlist.tsx`** ❌ **HIGH**
   - Watchlist component

5. **`frontend/src/components/QuoteCard.tsx`** ❌ **HIGH**
   - Individual quote display

6. **`frontend/src/components/CandlestickChart.tsx`** ❌ **MEDIUM**
   - Chart component

---

## 9. Recommended Next Steps

### Immediate Actions (Today)

1. **Start with Finnhub Service** 📍
   ```bash
   cd backend
   touch services/base.py services/finnhub_service.py
   ```

2. **Write Service Base Class**
   - Define common interface for all services
   - Add type hints and docstrings

3. **Implement Basic Finnhub Quote Fetch**
   - Just the `/quote` endpoint
   - Add caching integration
   - Add rate limiting

4. **Create Quotes Router**
   - Implement `GET /api/quotes/{symbol}`
   - Wire up Finnhub service
   - Add error handling

5. **Test Manually**
   ```bash
   # Start backend
   uvicorn main:app --reload
   
   # Test endpoint
   curl http://localhost:8000/api/quotes/AAPL
   ```

### This Week

1. Complete Finnhub + CoinGecko services
2. Complete quotes + historical routers
3. Write comprehensive tests
4. Update frontend to fetch real data

### This Month

1. Implement WebSocket support
2. Build frontend dashboard
3. Add candlestick charts
4. Deploy to production

---

## 10. Conclusion

### Project Status: **Strong Foundation, Ready for Core Development**

**Strengths:**
- ✅ Excellent architecture and design
- ✅ Comprehensive documentation
- ✅ Testing infrastructure in place
- ✅ All utilities and helpers ready
- ✅ Clear roadmap and vision

**Weaknesses:**
- ❌ Zero external API integrations
- ❌ No data endpoints implemented
- ❌ Frontend is still default template
- ❌ No actual business logic

### Estimated Time to v1.0

- **Phase 1 (Data Integration):** 2-3 weeks
- **Phase 2-3 (Historical + UI):** 2-3 weeks
- **Phase 4-6 (Charts + WS + Screener):** 3-4 weeks
- **Testing + Polish:** 1-2 weeks

**Total:** ~10-12 weeks to production-ready v1.0

### Risk Level: **LOW**

The project architecture is solid. The main risk is:
- API provider changes (especially yfinance)
- Rate limiting challenges
- WebSocket connection stability

All of these can be mitigated with the infrastructure already in place.

---

**Ready to implement? Start with `backend/services/finnhub_service.py`** 🚀
