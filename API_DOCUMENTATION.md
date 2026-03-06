# API Documentation

Complete API reference for Market Monitor backend endpoints.

## Base URL

- **Development:** `http://localhost:8000`
- **Production:** `https://api.market-monitor.example.com`

## Interactive Documentation

After starting the backend, access interactive API documentation:

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **OpenAPI JSON:** http://localhost:8000/openapi.json

The Swagger UI allows you to:
- View all endpoints and their parameters
- Try out API calls directly in the browser
- See request/response schemas
- Download OpenAPI specification

---

## Authentication

**Current:** No authentication required (personal use)

**Future:** JWT-based authentication planned

```http
Authorization: Bearer <token>
```

---

## Current Endpoints

### Root

#### GET /

Get API information and links.

**Response:**

```json
{
  "message": "Market Monitor API",
  "version": "0.1.0",
  "docs": "/docs",
  "health": "/health"
}
```

---

### Health & Status

#### GET /health

Get service health status and configured API providers.

**Response Model:** `HealthCheck`

**Response:**

```json
{
  "status": "healthy",
  "timestamp": "2026-03-06T14:00:00Z",
  "version": "0.1.0",
  "environment": "development",
  "services": {
    "finnhub": true,
    "fmp": true,
    "alpha_vantage": false,
    "twelve_data": false,
    "coingecko": true
  }
}
```

**Status Codes:**

- `200 OK` — Service is healthy
- `503 Service Unavailable` — Service is unhealthy (future)

---

#### GET /health/cache

Get cache statistics for all cache tiers.

**Response:**

```json
{
  "quotes": {
    "size": 15,
    "maxsize": 1000,
    "ttl": 60
  },
  "historical": {
    "size": 8,
    "maxsize": 500,
    "ttl": 3600
  },
  "fundamentals": {
    "size": 3,
    "maxsize": 200,
    "ttl": 86400
  }
}
```

**Fields:**

- `size` — Current number of cached items
- `maxsize` — Maximum cache capacity
- `ttl` — Time-to-live in seconds

**Use Case:**

Monitor cache performance and hit rates. High `size` values indicate good cache utilization.

---

#### GET /health/rate-limits

Get current rate limiting status for all API services.

**Response:**

```json
{
  "finnhub": {
    "calls_last_minute": 12,
    "limit": 50,
    "is_rate_limited": false,
    "rate_limit_until": null
  },
  "coingecko": {
    "calls_last_minute": 5,
    "limit": 50,
    "is_rate_limited": false,
    "rate_limit_until": null
  },
  "fmp": {
    "calls_last_minute": 2,
    "limit": 50,
    "is_rate_limited": true,
    "rate_limit_until": "2026-03-06T14:05:00Z"
  }
}
```

**Fields:**

- `calls_last_minute` — API calls in the last 60 seconds
- `limit` — Configured rate limit threshold
- `is_rate_limited` — Whether service is currently rate limited
- `rate_limit_until` — ISO timestamp when rate limit expires (null if not limited)

**Use Case:**

Debug rate limiting issues and monitor API usage patterns.

---

## Future Endpoints (Planned)

### Quotes

#### GET /api/quotes/{symbol}

Get real-time quote for a stock or cryptocurrency.

**Path Parameters:**

- `symbol` (string, required) — Stock ticker (e.g., `AAPL`) or crypto symbol (e.g., `bitcoin`)

**Query Parameters:**

- `source` (string, optional) — Force specific data source: `finnhub`, `coingecko`, `yfinance`

**Response:**

```json
{
  "symbol": "AAPL",
  "price": 150.25,
  "change": 2.50,
  "change_percent": 1.69,
  "volume": 50000000,
  "timestamp": "2026-03-06T14:00:00Z",
  "source": "finnhub",
  "cached": false
}
```

**Status Codes:**

- `200 OK` — Quote retrieved successfully
- `404 Not Found` — Symbol not found
- `429 Too Many Requests` — Rate limit exceeded
- `503 Service Unavailable` — All data sources failed

**Caching:**

- TTL: 60 seconds
- Cache key: `{symbol}`

**Example:**

```bash
curl http://localhost:8000/api/quotes/AAPL
```

---

#### GET /api/quotes/batch

Get quotes for multiple symbols in one request.

**Query Parameters:**

- `symbols` (string, required) — Comma-separated list of symbols (max 50)

**Response:**

```json
{
  "quotes": [
    {
      "symbol": "AAPL",
      "price": 150.25,
      "change": 2.50,
      "change_percent": 1.69,
      "timestamp": "2026-03-06T14:00:00Z"
    },
    {
      "symbol": "GOOGL",
      "price": 2800.00,
      "change": -15.50,
      "change_percent": -0.55,
      "timestamp": "2026-03-06T14:00:00Z"
    }
  ],
  "count": 2,
  "timestamp": "2026-03-06T14:00:00Z"
}
```

**Example:**

```bash
curl "http://localhost:8000/api/quotes/batch?symbols=AAPL,GOOGL,MSFT"
```

---

### Historical Data

#### GET /api/historical/{symbol}

Get historical OHLCV (Open, High, Low, Close, Volume) candles.

**Path Parameters:**

- `symbol` (string, required) — Stock ticker or crypto symbol

**Query Parameters:**

- `interval` (string, required) — Candle interval: `1m`, `5m`, `15m`, `1h`, `4h`, `1d`, `1w`, `1M`
- `from` (string, optional) — Start date (ISO 8601 or YYYY-MM-DD)
- `to` (string, optional) — End date (ISO 8601 or YYYY-MM-DD)
- `limit` (int, optional) — Max number of candles (default: 100, max: 5000)

**Response:**

```json
{
  "symbol": "AAPL",
  "interval": "1d",
  "candles": [
    {
      "timestamp": "2026-03-01T00:00:00Z",
      "open": 148.50,
      "high": 151.00,
      "low": 147.80,
      "close": 150.25,
      "volume": 45000000
    },
    {
      "timestamp": "2026-03-02T00:00:00Z",
      "open": 150.25,
      "high": 152.50,
      "low": 149.00,
      "close": 151.75,
      "volume": 52000000
    }
  ],
  "count": 2,
  "source": "yfinance"
}
```

**Caching:**

- TTL: 3600 seconds (1 hour)
- Cache key: `{symbol}_{interval}_{from}_{to}`

**Example:**

```bash
curl "http://localhost:8000/api/historical/AAPL?interval=1d&limit=30"
```

---

### Screener

#### GET /api/screener

Screen stocks or cryptocurrencies based on criteria.

**Query Parameters:**

- `asset_type` (string, required) — `stock` or `crypto`
- `min_price` (float, optional) — Minimum price
- `max_price` (float, optional) — Maximum price
- `min_volume` (int, optional) — Minimum 24h volume
- `min_change_percent` (float, optional) — Minimum % change (e.g., `5` for +5%)
- `max_change_percent` (float, optional) — Maximum % change (e.g., `-5` for -5%)
- `limit` (int, optional) — Max results (default: 50, max: 200)

**Response:**

```json
{
  "results": [
    {
      "symbol": "AAPL",
      "price": 150.25,
      "change_percent": 5.2,
      "volume": 50000000,
      "market_cap": 2500000000000
    },
    {
      "symbol": "TSLA",
      "price": 185.50,
      "change_percent": 8.5,
      "volume": 75000000,
      "market_cap": 600000000000
    }
  ],
  "count": 2,
  "criteria": {
    "asset_type": "stock",
    "min_change_percent": 5.0
  }
}
```

**Example:**

```bash
curl "http://localhost:8000/api/screener?asset_type=stock&min_change_percent=5&limit=10"
```

---

#### POST /api/screener/technical

Screen with technical indicators (RSI, MACD, SMA).

**Request Body:**

```json
{
  "asset_type": "stock",
  "indicators": [
    {
      "type": "rsi",
      "period": 14,
      "min": 30,
      "max": 70
    },
    {
      "type": "sma_cross",
      "short_period": 50,
      "long_period": 200,
      "direction": "bullish"
    }
  ],
  "limit": 50
}
```

**Response:**

```json
{
  "results": [
    {
      "symbol": "AAPL",
      "price": 150.25,
      "indicators": {
        "rsi_14": 45.2,
        "sma_50": 145.00,
        "sma_200": 140.00,
        "sma_cross": "bullish"
      },
      "signal": "buy"
    }
  ],
  "count": 1
}
```

**Supported Indicators:**

- `rsi` — Relative Strength Index
- `macd` — Moving Average Convergence Divergence
- `sma_cross` — Simple Moving Average crossover
- `ema` — Exponential Moving Average
- `bb` — Bollinger Bands

**Example:**

```bash
curl -X POST http://localhost:8000/api/screener/technical \
  -H "Content-Type: application/json" \
  -d '{
    "asset_type": "stock",
    "indicators": [{"type": "rsi", "period": 14, "min": 30}],
    "limit": 10
  }'
```

---

### WebSocket

#### WS /ws/quotes

Real-time price updates via WebSocket.

**Connection:**

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/quotes');

ws.onopen = () => {
  // Subscribe to symbols
  ws.send(JSON.stringify({
    action: 'subscribe',
    symbols: ['AAPL', 'GOOGL', 'bitcoin']
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Quote update:', data);
};
```

**Subscribe Message:**

```json
{
  "action": "subscribe",
  "symbols": ["AAPL", "GOOGL"]
}
```

**Unsubscribe Message:**

```json
{
  "action": "unsubscribe",
  "symbols": ["AAPL"]
}
```

**Price Update Message (from server):**

```json
{
  "type": "quote",
  "symbol": "AAPL",
  "price": 150.25,
  "change": 2.50,
  "change_percent": 1.69,
  "volume": 50000000,
  "timestamp": "2026-03-06T14:00:00Z"
}
```

**Error Message (from server):**

```json
{
  "type": "error",
  "message": "Symbol not found",
  "symbol": "INVALID"
}
```

**Ping/Pong:**

Server sends ping every 30 seconds:

```json
{"type": "ping"}
```

Client should respond with pong:

```json
{"type": "pong"}
```

**Rate Limiting:**

- Max 100 concurrent connections per IP
- Max 50 symbols per connection
- Reconnect with exponential backoff if disconnected

---

## Error Responses

All endpoints return standardized error responses.

### Error Response Model

```json
{
  "error": "ErrorType",
  "message": "Human-readable error message",
  "detail": {
    "additional": "error details"
  },
  "timestamp": "2026-03-06T14:00:00Z"
}
```

### Common Error Types

#### 400 Bad Request

Invalid request parameters.

```json
{
  "error": "ValidationError",
  "message": "Invalid interval parameter",
  "detail": {
    "field": "interval",
    "allowed_values": ["1m", "5m", "15m", "1h", "4h", "1d", "1w", "1M"]
  },
  "timestamp": "2026-03-06T14:00:00Z"
}
```

#### 404 Not Found

Resource not found.

```json
{
  "error": "NotFound",
  "message": "Symbol not found",
  "detail": {
    "symbol": "INVALID",
    "searched_sources": ["finnhub", "coingecko", "yfinance"]
  },
  "timestamp": "2026-03-06T14:00:00Z"
}
```

#### 429 Too Many Requests

Rate limit exceeded.

```json
{
  "error": "RateLimitExceeded",
  "message": "API rate limit exceeded. Please try again later.",
  "detail": {
    "retry_after": 60,
    "limit": 50,
    "window": "1 minute"
  },
  "timestamp": "2026-03-06T14:00:00Z"
}
```

#### 500 Internal Server Error

Unexpected server error.

```json
{
  "error": "InternalServerError",
  "message": "An unexpected error occurred",
  "detail": {
    "request_id": "abc123"
  },
  "timestamp": "2026-03-06T14:00:00Z"
}
```

#### 503 Service Unavailable

All data sources failed.

```json
{
  "error": "ServiceUnavailable",
  "message": "All data sources failed. Please try again later.",
  "detail": {
    "failed_sources": ["finnhub", "yfinance", "fmp"],
    "retry_after": 300
  },
  "timestamp": "2026-03-06T14:00:00Z"
}
```

---

## Rate Limiting

### Per-Endpoint Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| GET /api/quotes/{symbol} | 50 requests | 1 minute |
| GET /api/quotes/batch | 10 requests | 1 minute |
| GET /api/historical/{symbol} | 30 requests | 1 minute |
| GET /api/screener | 10 requests | 1 minute |
| POST /api/screener/technical | 5 requests | 1 minute |

### Rate Limit Headers

Response headers include rate limit info:

```http
X-RateLimit-Limit: 50
X-RateLimit-Remaining: 35
X-RateLimit-Reset: 1709735400
```

### Exceeding Limits

When rate limit is exceeded, API returns `429 Too Many Requests`:

```json
{
  "error": "RateLimitExceeded",
  "message": "Rate limit exceeded. Please try again later.",
  "detail": {
    "retry_after": 60
  }
}
```

**Retry Strategy:**

1. Wait for `retry_after` seconds
2. Implement exponential backoff: wait × 2^(retry_count)
3. Max retry wait: 5 minutes

---

## Pagination

Large result sets use cursor-based pagination.

### Request

```http
GET /api/screener?limit=50&cursor=abc123
```

### Response

```json
{
  "results": [...],
  "count": 50,
  "next_cursor": "def456",
  "has_more": true
}
```

### Next Page

```http
GET /api/screener?limit=50&cursor=def456
```

---

## CORS

Cross-Origin Resource Sharing (CORS) is enabled for configured origins.

**Allowed Origins:**

- Development: `http://localhost:3000`, `http://192.168.64.15:3000`
- Production: Set via `CORS_ORIGINS` environment variable

**Allowed Methods:**

- GET, POST, PUT, DELETE, OPTIONS

**Allowed Headers:**

- All standard headers
- Custom headers: `X-Request-ID`

---

## Versioning

**Current:** v0.1.0 (no versioning in URL yet)

**Future:** API versioning via URL path:

```http
GET /api/v1/quotes/AAPL
GET /api/v2/quotes/AAPL
```

Or via header:

```http
GET /api/quotes/AAPL
Accept: application/vnd.market-monitor.v1+json
```

---

## Testing the API

### Using curl

```bash
# Get health status
curl http://localhost:8000/health

# Get cache stats
curl http://localhost:8000/health/cache

# Get rate limit status
curl http://localhost:8000/health/rate-limits

# Pretty print JSON
curl http://localhost:8000/health | jq
```

### Using httpie

```bash
# Install httpie
pip install httpie

# Get health status
http localhost:8000/health

# With query parameters
http localhost:8000/api/quotes/AAPL source=finnhub

# POST request
http POST localhost:8000/api/screener/technical \
  asset_type=stock \
  indicators:='[{"type":"rsi","period":14}]' \
  limit=10
```

### Using Python requests

```python
import requests

# Get health status
response = requests.get('http://localhost:8000/health')
print(response.json())

# Get quote (when implemented)
response = requests.get('http://localhost:8000/api/quotes/AAPL')
if response.status_code == 200:
    quote = response.json()
    print(f"AAPL: ${quote['price']}")
elif response.status_code == 429:
    print("Rate limit exceeded!")
```

### Using JavaScript fetch

```javascript
// Get health status
fetch('http://localhost:8000/health')
  .then(response => response.json())
  .then(data => console.log(data));

// Get quote with error handling
async function getQuote(symbol) {
  try {
    const response = await fetch(`http://localhost:8000/api/quotes/${symbol}`);
    
    if (!response.ok) {
      const error = await response.json();
      console.error('API Error:', error);
      return null;
    }
    
    const quote = await response.json();
    return quote;
  } catch (error) {
    console.error('Network Error:', error);
    return null;
  }
}
```

---

## OpenAPI Specification

Download the complete OpenAPI specification:

```bash
curl http://localhost:8000/openapi.json > market-monitor-api.json
```

Use with code generators:

```bash
# Generate Python client
openapi-generator-cli generate \
  -i market-monitor-api.json \
  -g python \
  -o ./python-client

# Generate TypeScript client
openapi-generator-cli generate \
  -i market-monitor-api.json \
  -g typescript-axios \
  -o ./typescript-client
```

---

## Support

- **Documentation:** See `/docs` endpoint for interactive API explorer
- **Issues:** Open an issue on GitHub
- **Questions:** Check existing documentation first

---

**Last Updated:** March 6, 2026  
**API Version:** 0.1.0
