# Market Monitor - Implementation Checklist

## 📊 Current Progress: 15% Complete

### ✅ Infrastructure (100% Complete)
- [x] FastAPI application setup
- [x] Routing and middleware
- [x] Multi-tier caching system (CacheManager)
- [x] Rate limiting system (RateLimiter)
- [x] Structured logging
- [x] Health check endpoints (3 endpoints)
- [x] Pydantic v2 data models
- [x] CORS configuration
- [x] Error handling
- [x] Test infrastructure (pytest + pytest-asyncio)
- [x] Documentation (README, API docs, deployment guides)

### ❌ Core Functionality (0% Complete)

#### Backend Services (CRITICAL - 0/4 Complete)
- [ ] `services/base.py` - Base service class
- [ ] `services/finnhub_service.py` - Stock quotes + historical data
- [ ] `services/coingecko_service.py` - Crypto quotes + historical data
- [ ] `services/yfinance_service.py` - Fallback historical data
- [ ] `services/fmp_service.py` - Fundamentals data

#### API Endpoints (CRITICAL - 0/4 Complete)
- [ ] `routers/quotes.py` - GET /api/quotes/{symbol}, GET /api/quotes/batch
- [ ] `routers/historical.py` - GET /api/historical/{symbol}
- [ ] `routers/screener.py` - GET /api/screener, POST /api/screener/technical
- [ ] `routers/websocket.py` - WS /ws/quotes

#### WebSocket Support (0/2 Complete)
- [ ] `services/websocket_manager.py` - Manage Finnhub WebSocket
- [ ] Backend WebSocket endpoint implementation

#### Frontend (0% Complete)
- [ ] API client (`src/api/client.ts`)
- [ ] State management (Zustand stores)
- [ ] Dashboard component
- [ ] Watchlist component
- [ ] Quote cards
- [ ] Candlestick charts
- [ ] WebSocket client

---

## 🎯 Next 5 Tasks (Priority Order)

### 1. Create Service Base Class (1 hour)
**File:** `backend/services/base.py`

```python
from abc import ABC, abstractmethod
from models import Quote, HistoricalData

class BaseDataService(ABC):
    @abstractmethod
    async def get_quote(self, symbol: str) -> Quote:
        """Fetch real-time quote."""
        pass
    
    @abstractmethod
    async def get_historical(self, symbol: str, interval: str) -> HistoricalData:
        """Fetch historical OHLCV data."""
        pass
```

**Tests:** `tests/test_base_service.py`

---

### 2. Implement Finnhub Service (4-6 hours)
**File:** `backend/services/finnhub_service.py`

```python
class FinnhubService(BaseDataService):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://finnhub.io/api/v1"
        self.client = httpx.AsyncClient()
    
    async def get_quote(self, symbol: str) -> Quote:
        """
        Fetch quote from Finnhub /quote endpoint.
        
        API Response: {"c": 150.25, "pc": 148.00, "h": 151, "l": 147.5}
        - c: current price
        - pc: previous close
        - h: high
        - l: low
        """
        # Check cache first
        cache_key = f"{symbol}"
        if cache_key in cache_manager.quotes_cache:
            return cache_manager.quotes_cache[cache_key]
        
        # Check rate limit
        if not rate_limiter.can_call("finnhub"):
            raise RateLimitError("Finnhub rate limit exceeded")
        
        # Make API call
        url = f"{self.base_url}/quote"
        params = {"symbol": symbol, "token": self.api_key}
        response = await self.client.get(url, params=params)
        
        # Record rate limit
        rate_limiter.record_call("finnhub")
        
        # Transform to Quote model
        data = response.json()
        quote = self._transform_quote(symbol, data)
        
        # Cache result
        cache_manager.quotes_cache[cache_key] = quote
        
        return quote
```

**Tests:** `tests/test_finnhub_service.py`
- Mock successful API call
- Test caching
- Test rate limiting
- Test error handling
- Test data transformation

---

### 3. Create Quotes Router (3-4 hours)
**File:** `backend/routers/quotes.py`

```python
from fastapi import APIRouter, HTTPException, Query
from services.finnhub_service import FinnhubService
from services.yfinance_service import YFinanceService
from models import Quote

router = APIRouter(prefix="/api/quotes", tags=["Quotes"])

@router.get("/{symbol}", response_model=Quote)
async def get_quote(
    symbol: str,
    source: Optional[str] = Query(None, description="Force specific source")
):
    """
    Get real-time quote for a symbol.
    
    Tries providers in order: Finnhub -> yfinance -> FMP
    """
    try:
        # Try Finnhub first
        finnhub = FinnhubService(api_key=settings.finnhub_api_key)
        return await finnhub.get_quote(symbol)
    except Exception as e:
        logger.warning("finnhub_failed", symbol=symbol, error=str(e))
        
        # Fallback to yfinance
        try:
            yfinance = YFinanceService()
            return await yfinance.get_quote(symbol)
        except Exception as e2:
            logger.error("all_services_failed", symbol=symbol)
            raise HTTPException(status_code=503, detail="All data sources failed")
```

**Update:** `backend/main.py`
```python
from routers.quotes import router as quotes_router
app.include_router(quotes_router)
```

**Tests:** `tests/test_quotes_router.py`
- Test successful quote fetch
- Test fallback logic
- Test error responses
- Test caching via integration test

---

### 4. Implement CoinGecko Service (3-4 hours)
**File:** `backend/services/coingecko_service.py`

```python
class CoinGeckoService(BaseDataService):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.coingecko.com/api/v3"
        self.client = httpx.AsyncClient()
    
    async def get_quote(self, symbol: str) -> Quote:
        """
        Fetch crypto quote from CoinGecko /simple/price endpoint.
        
        API Response: {
            "bitcoin": {
                "usd": 42000,
                "usd_24h_change": 2.5,
                "usd_24h_vol": 25000000000,
                "usd_market_cap": 800000000000
            }
        }
        """
        # Check cache
        cache_key = f"{symbol}"
        if cache_key in cache_manager.quotes_cache:
            return cache_manager.quotes_cache[cache_key]
        
        # Check rate limit
        if not rate_limiter.can_call("coingecko"):
            raise RateLimitError("CoinGecko rate limit exceeded")
        
        # Make API call
        url = f"{self.base_url}/simple/price"
        params = {
            "ids": symbol,  # e.g., "bitcoin"
            "vs_currencies": "usd",
            "include_24hr_change": "true",
            "include_24hr_vol": "true",
            "include_market_cap": "true",
        }
        headers = {"x-cg-demo-api-key": self.api_key}
        
        response = await self.client.get(url, params=params, headers=headers)
        rate_limiter.record_call("coingecko")
        
        # Transform to Quote model
        data = response.json()
        quote = self._transform_quote(symbol, data)
        
        # Cache result
        cache_manager.quotes_cache[cache_key] = quote
        
        return quote
```

**Tests:** `tests/test_coingecko_service.py`

---

### 5. Write Integration Tests (2-3 hours)
**File:** `tests/test_quotes_integration.py`

```python
@pytest.mark.integration
class TestQuotesIntegration:
    """Integration tests for quote endpoints."""
    
    def test_get_stock_quote(self, client: TestClient):
        """Test fetching stock quote."""
        response = client.get("/api/quotes/AAPL")
        assert response.status_code == 200
        
        data = response.json()
        assert data["symbol"] == "AAPL"
        assert "price" in data
        assert "source" in data
    
    def test_get_crypto_quote(self, client: TestClient):
        """Test fetching crypto quote."""
        response = client.get("/api/quotes/bitcoin")
        assert response.status_code == 200
        
        data = response.json()
        assert data["symbol"] == "bitcoin"
        assert data["asset_type"] == "crypto"
    
    def test_quote_caching(self, client: TestClient):
        """Test that quotes are cached."""
        # First request
        response1 = client.get("/api/quotes/AAPL")
        
        # Second request (should hit cache)
        response2 = client.get("/api/quotes/AAPL")
        
        # Both should return same data
        assert response1.json() == response2.json()
    
    def test_invalid_symbol(self, client: TestClient):
        """Test handling of invalid symbol."""
        response = client.get("/api/quotes/INVALID_SYMBOL_12345")
        assert response.status_code == 404
```

---

## 📋 Implementation Order (Recommended)

### Week 1: Core Data Integration
- [ ] Day 1: Base service + Finnhub service
- [ ] Day 2: Finnhub tests + Quotes router
- [ ] Day 3: CoinGecko service + tests
- [ ] Day 4: yfinance service + fallback logic
- [ ] Day 5: Integration tests + bug fixes

**Deliverable:** Working `/api/quotes/AAPL` and `/api/quotes/bitcoin` endpoints

### Week 2: Historical Data
- [ ] Day 1-2: Historical data in Finnhub + CoinGecko services
- [ ] Day 3: Historical router (`GET /api/historical/{symbol}`)
- [ ] Day 4: Tests + documentation
- [ ] Day 5: Buffer for bug fixes

**Deliverable:** Working historical data endpoint with caching

### Week 3: Frontend Foundation
- [ ] Day 1: Install dependencies (Zustand, Recharts, Axios)
- [ ] Day 2: API client + Zustand stores
- [ ] Day 3-4: Dashboard layout + Watchlist component
- [ ] Day 5: Quote cards with real data

**Deliverable:** Functional dashboard showing real quotes

### Week 4: Charts + Polish
- [ ] Day 1-2: Candlestick chart component
- [ ] Day 3: Multiple timeframes
- [ ] Day 4: Responsive design + dark mode
- [ ] Day 5: Testing + documentation

**Deliverable:** Interactive charts with historical data

---

## 🧪 Testing Checklist

### Backend Tests (Target: 80%+ coverage)
- [ ] Unit tests for each service
- [ ] Integration tests for endpoints
- [ ] Cache behavior tests
- [ ] Rate limiting tests
- [ ] Error handling tests
- [ ] Fallback chain tests

### Frontend Tests (Target: 60%+ coverage)
- [ ] Component rendering tests
- [ ] State management tests
- [ ] API client tests
- [ ] User interaction tests

---

## 📝 Documentation Updates Needed
- [ ] Update API_DOCUMENTATION.md with actual endpoints
- [ ] Add service documentation
- [ ] Update README.md with setup instructions
- [ ] Add troubleshooting guide
- [ ] Update CHANGELOG.md with each release

---

## 🚀 Quick Start Commands

```bash
# Backend Development
cd backend
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Frontend Development
cd frontend
npm run dev

# Run Tests
cd backend && pytest -v
cd frontend && npm test

# Check Coverage
cd backend && pytest --cov=. --cov-report=html
```

---

**Start Here:** Create `backend/services/base.py` and `backend/services/finnhub_service.py`
