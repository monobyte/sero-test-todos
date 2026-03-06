# Backend Architecture

## Overview

The Market Monitor backend is built with FastAPI following a layered architecture pattern. It provides a robust, type-safe API for real-time and historical financial market data, integrating multiple free-tier data sources with intelligent fallback and caching strategies.

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                        FastAPI App                          │
│                    (main.py + routers/)                     │
├─────────────────────────────────────────────────────────────┤
│                      Middleware Layer                        │
│              CORS │ Logging │ Error Handling                │
├─────────────────────────────────────────────────────────────┤
│                      Service Layer                           │
│        (services/) - Business Logic & API Integration       │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Finnhub    │  │  CoinGecko   │  │   yfinance   │     │
│  │   Service    │  │   Service    │  │   Service    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│         │                 │                  │              │
│         └─────────────────┴──────────────────┘              │
│                           │                                 │
├───────────────────────────┼─────────────────────────────────┤
│                    Utility Layer                            │
│         Cache Manager │ Rate Limiter │ Logger              │
├─────────────────────────────────────────────────────────────┤
│                    External APIs                            │
│      Finnhub │ CoinGecko │ FMP │ Alpha Vantage │ etc.     │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Application Entry Point (`main.py`)

**Responsibilities:**
- FastAPI app initialization
- CORS configuration
- Global exception handlers
- Middleware registration
- Router mounting
- Lifespan management (startup/shutdown)

**Key Features:**
- Structured request/response logging
- Automatic API documentation (OpenAPI/Swagger)
- Type-safe with Pydantic models
- Environment-based configuration

### 2. Configuration (`config.py`)

**Responsibilities:**
- Load environment variables from `.env`
- Provide typed settings via Pydantic
- Validate configuration on startup

**Settings Categories:**
- Application (host, port, environment)
- CORS origins
- API keys for external services
- Cache TTLs
- Rate limiting parameters
- WebSocket configuration

### 3. Models (`models/`)

**Purpose:** Define type-safe data structures for the entire application.

#### `base.py`
- `HealthCheck`: Service health status
- `ErrorResponse`: Standard error format
- `SuccessResponse`: Standard success format

#### `market.py`
- `AssetType`: Enum for stock/crypto/ETF/index
- `MarketStatus`: Enum for market open/closed states
- `Quote`: Real-time price quote
- `OHLCV`: Single candlestick data point
- `HistoricalData`: Collection of OHLCV candles

**Benefits:**
- Automatic request/response validation
- OpenAPI schema generation
- Type hints for IDE support
- Serialization/deserialization

### 4. Routers (`routers/`)

**Purpose:** Define API endpoints and handle HTTP requests.

#### `health.py` (Current)
- `GET /health` - Service health check
- `GET /health/cache` - Cache statistics
- `GET /health/rate-limits` - Rate limit status

#### Future Routers
- `quotes.py` - Real-time quote endpoints
- `historical.py` - Historical data endpoints
- `screener.py` - Stock/crypto screening
- `websocket.py` - WebSocket connections for live feeds

**Pattern:**
```python
@router.get("/endpoint", response_model=ResponseModel)
async def endpoint_handler() -> ResponseModel:
    # 1. Validate request (automatic via Pydantic)
    # 2. Call service layer
    # 3. Return response (automatic serialization)
```

### 5. Services (`services/`)

**Purpose:** Implement business logic and external API integration.

**Planned Services:**
- `finnhub_service.py` - Finnhub API client
- `coingecko_service.py` - CoinGecko API client
- `yfinance_service.py` - yfinance wrapper
- `fmp_service.py` - Financial Modeling Prep client

**Service Pattern:**
```python
class DataService:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.AsyncClient()
    
    async def get_quote(self, symbol: str) -> Quote:
        # 1. Check rate limiter
        # 2. Check cache
        # 3. Make API call if needed
        # 4. Handle errors with fallback
        # 5. Update cache
        # 6. Return data
```

**Error Handling Strategy:**
1. Primary source (e.g., Finnhub)
2. If rate limited/error → Fallback source (e.g., yfinance)
3. If all fail → Return cached data (if available)
4. If no cache → Return structured error

### 6. Utilities (`utils/`)

#### `cache.py` - Cache Manager
**Purpose:** Reduce API calls with intelligent caching.

**Strategy:**
- Separate caches for quotes, historical, fundamentals
- Different TTLs based on data freshness requirements
- In-memory (cachetools TTLCache)

**Usage:**
```python
# Check cache first
cached = cache_manager.get_quote(symbol)
if cached:
    return cached

# Fetch from API
data = await api_call(symbol)

# Store in cache
cache_manager.set_quote(symbol, data)
```

#### `rate_limiter.py` - Rate Limiter
**Purpose:** Prevent exceeding free-tier API limits.

**Features:**
- Per-service tracking
- Sliding window (1 minute)
- Manual rate limit setting (for 429 responses)
- Statistics for monitoring

**Usage:**
```python
if not rate_limiter.can_call("finnhub"):
    # Use fallback or return error
    return await fallback_source()

# Make API call
response = await api_call()
rate_limiter.record_call("finnhub")
```

#### `logger.py` - Structured Logger
**Purpose:** Consistent, contextual logging.

**Features:**
- Structured logs (JSON in production, pretty in dev)
- Contextual information (request ID, user, etc.)
- Log levels (DEBUG, INFO, WARNING, ERROR)

**Usage:**
```python
logger.info(
    "quote_fetched",
    symbol=symbol,
    source="finnhub",
    cached=False,
    duration_ms=123.45
)
```

## Data Flow

### Example: Fetching a Stock Quote

```
1. Client Request
   GET /api/quotes/AAPL
   │
   ├─→ 2. Router (routers/quotes.py)
   │      - Validate request
   │      - Extract symbol
   │
   ├─→ 3. Service (services/finnhub_service.py)
   │      │
   │      ├─→ 4. Rate Limiter Check
   │      │      - Can call Finnhub?
   │      │
   │      ├─→ 5. Cache Check
   │      │      - In cache and fresh?
   │      │      - If yes → return cached
   │      │
   │      ├─→ 6. API Call
   │      │      - httpx.AsyncClient
   │      │      - Finnhub REST API
   │      │      - Handle errors
   │      │
   │      ├─→ 7. Fallback (if error)
   │      │      - Try yfinance
   │      │      - Try FMP
   │      │
   │      ├─→ 8. Transform Data
   │      │      - Convert to Quote model
   │      │      - Standardize format
   │      │
   │      └─→ 9. Update Cache
   │             - Store for future requests
   │
   └─→ 10. Response
          - Return Quote model
          - Automatic JSON serialization
```

## Error Handling Strategy

### Levels of Fallback

1. **Primary Source** (e.g., Finnhub)
   - Fast, real-time, reliable
   
2. **Rate Limited?**
   → Try **Secondary Source** (e.g., yfinance)
   
3. **Secondary Failed?**
   → Return **Cached Data** (if available, even if stale)
   
4. **No Cache?**
   → Return **Error Response**
   ```json
   {
     "error": "DataUnavailable",
     "message": "Unable to fetch quote. All sources failed.",
     "detail": {
       "finnhub": "Rate limited",
       "yfinance": "Connection timeout",
       "cache": "No cached data"
     }
   }
   ```

### Rate Limit Handling

When receiving HTTP 429 (Too Many Requests):
```python
if response.status_code == 429:
    retry_after = int(response.headers.get("Retry-After", 60))
    rate_limiter.set_rate_limit(service, retry_after)
    # Try fallback source
```

## WebSocket Architecture (Future)

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend Client                        │
│                    (WebSocket connection)                   │
└────────────────────────────┬────────────────────────────────┘
                             │
                             │ WS: /ws/quotes
                             │
┌────────────────────────────┴────────────────────────────────┐
│                    FastAPI WebSocket Handler                │
│                   (routers/websocket.py)                    │
│                                                              │
│  - Manage connections                                       │
│  - Subscribe to symbols                                     │
│  - Broadcast updates                                        │
└────────────────────────────┬────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
   ┌──────────▼─────────┐        ┌─────────▼──────────┐
   │  Finnhub WebSocket │        │  Binance WebSocket │
   │   (Stock quotes)   │        │   (Crypto prices)  │
   └────────────────────┘        └────────────────────┘
```

**Flow:**
1. Client connects to `/ws/quotes`
2. Sends subscription message: `{"action": "subscribe", "symbols": ["AAPL", "BTC-USD"]}`
3. Backend maintains upstream connections to Finnhub/Binance
4. On price update from external source → Broadcast to subscribed clients
5. Client can unsubscribe or disconnect

## Performance Optimizations

### 1. Caching Strategy
- **Quotes**: 60s TTL (balance freshness vs API calls)
- **Historical**: 1h TTL (daily candles don't change)
- **Fundamentals**: 24h TTL (company data is static)

### 2. Rate Limiting
- Prevents API bans
- Automatic fallback to secondary sources
- Per-service tracking

### 3. Async/Await
- Non-blocking I/O for API calls
- Concurrent request handling
- WebSocket support

### 4. Connection Pooling
- httpx.AsyncClient with persistent connections
- Reduces connection overhead

## Security Considerations

### 1. API Keys
- Never commit `.env` to version control
- Use environment variables
- Rotate keys periodically

### 2. CORS
- Whitelist specific origins
- No wildcard (`*`) in production

### 3. Rate Limiting
- Protect backend from abuse
- Implement per-IP rate limiting (future)

### 4. Input Validation
- Pydantic models validate all inputs
- Prevent SQL injection (when DB added)
- Sanitize user input

## Monitoring & Observability

### Structured Logging
All events are logged with context:
```json
{
  "event": "quote_fetched",
  "symbol": "AAPL",
  "source": "finnhub",
  "cached": false,
  "duration_ms": 123.45,
  "timestamp": "2026-03-06T14:00:00Z",
  "level": "info"
}
```

### Health Checks
- `/health` - Overall service status
- `/health/cache` - Cache hit rates
- `/health/rate-limits` - API usage per service

### Future: Metrics
- Prometheus integration
- Grafana dashboards
- Alert on rate limit violations

## Deployment Considerations

### Environment Variables
Production should use:
- `APP_ENV=production`
- Secrets manager for API keys
- `LOG_LEVEL=WARNING` or `ERROR`

### Reverse Proxy
- nginx or Caddy for HTTPS
- Rate limiting at proxy level
- Load balancing (if scaling)

### Database (Future)
- PostgreSQL for persistent data
- Store watchlists, user preferences
- Cache historical data

## Next Steps

1. **Implement Services** (`services/`)
   - Finnhub client
   - CoinGecko client
   - yfinance wrapper

2. **Add Endpoints** (`routers/`)
   - `/api/quotes` - Real-time quotes
   - `/api/historical` - OHLCV data
   - `/api/screener` - Stock screening

3. **WebSocket Support** (`routers/websocket.py`)
   - Live price feeds
   - Connection management

4. **Testing**
   - Unit tests for services
   - Integration tests for endpoints
   - Load testing for WebSocket

5. **Documentation**
   - API usage examples
   - Rate limit best practices
   - Deployment guide
