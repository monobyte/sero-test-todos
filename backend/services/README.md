# Services Layer

The services layer provides external API integrations with built-in caching, rate limiting, error handling, and retry logic.

## Base Service

`BaseService` is an abstract base class that provides common functionality for all API service implementations.

### Features

- **HTTP Client Management**: Async HTTP client using `httpx` with configurable timeouts
- **Caching Integration**: Automatic caching with appropriate TTLs for different data types
- **Rate Limiting**: Prevents exceeding free-tier API quotas
- **Error Handling**: Comprehensive error handling with structured logging
- **Retry Logic**: Exponential backoff for transient failures
- **Request/Response Logging**: Detailed logging for debugging and monitoring

### Creating a New Service

To create a new service, subclass `BaseService` and implement the required abstract methods:

```python
from services.base import BaseService, CacheType

class MyAPIService(BaseService):
    """Service for MyAPI integration."""
    
    SERVICE_NAME = "myapi"  # Unique service identifier
    
    def _get_base_url(self) -> str:
        """Return API base URL."""
        return "https://api.myapi.com/v1"
    
    def _get_api_key(self) -> str:
        """Return API key from settings."""
        from config import settings
        return settings.myapi_api_key
    
    async def get_quote(self, symbol: str) -> dict:
        """
        Get quote for a symbol.
        
        Args:
            symbol: Ticker symbol
            
        Returns:
            Quote data dictionary
        """
        return await self._make_request(
            method="GET",
            endpoint=f"/quote/{symbol}",
            cache_type=CacheType.QUOTE,
            cache_key_parts=["quote", symbol],
        )
```

### Making API Requests

Use the `_make_request` method to make HTTP requests with automatic caching, rate limiting, and retry logic:

```python
# Simple GET request
data = await self._make_request("GET", "/endpoint")

# GET with query parameters
data = await self._make_request(
    "GET",
    "/endpoint",
    params={"symbol": "AAPL", "interval": "1d"}
)

# POST with JSON body
data = await self._make_request(
    "POST",
    "/endpoint",
    json_data={"key": "value"}
)

# With caching (recommended for frequently accessed data)
data = await self._make_request(
    "GET",
    f"/quote/{symbol}",
    cache_type=CacheType.QUOTE,  # or HISTORICAL, FUNDAMENTAL
    cache_key_parts=["quote", symbol],  # Used to build unique cache key
)
```

### Cache Types

Three cache types with different TTLs:

- **`CacheType.QUOTE`**: For real-time quotes (TTL: 60 seconds)
- **`CacheType.HISTORICAL`**: For historical data (TTL: 1 hour)
- **`CacheType.FUNDAMENTAL`**: For fundamental data (TTL: 24 hours)

### Error Handling

The base service provides specific exception types:

```python
from services.base import (
    ServiceError,           # Base exception
    RateLimitError,        # Rate limit exceeded (429)
    AuthenticationError,   # Auth failed (401)
    NotFoundError,         # Resource not found (404)
    NetworkError,          # Network/connection error
)

try:
    data = await service.get_quote("AAPL")
except RateLimitError as e:
    print(f"Rate limited. Retry after {e.retry_after}s")
except AuthenticationError as e:
    print(f"Authentication failed. Check API key.")
except NotFoundError as e:
    print(f"Resource '{e.resource}' not found")
except NetworkError as e:
    print(f"Network error: {e.original_error}")
except ServiceError as e:
    print(f"Service error: {e.message}")
```

### Configuration

Override class attributes to customize behavior:

```python
class MyAPIService(BaseService):
    SERVICE_NAME = "myapi"
    
    # Custom retry configuration
    MAX_RETRIES = 5  # Default: 3
    RETRY_BACKOFF_FACTOR = 1.5  # Default: 2.0 (1s, 2s, 4s)
    RETRY_STATUSES = {429, 500, 502, 503, 504}  # Retry on these codes
    
    # Custom timeout
    REQUEST_TIMEOUT = 60.0  # Default: 30.0 seconds
```

### Custom Headers

Override `_get_default_headers` to add custom headers:

```python
def _get_default_headers(self) -> Dict[str, str]:
    """Add custom headers."""
    headers = super()._get_default_headers()
    headers["X-API-Key"] = self._get_api_key()
    return headers
```

### Resource Cleanup

Always close the service when done, or use as async context manager:

```python
# Manual cleanup
service = MyAPIService()
try:
    data = await service.get_quote("AAPL")
finally:
    await service.close()

# Recommended: Use async context manager
async with MyAPIService() as service:
    data = await service.get_quote("AAPL")
# Automatically closed after the block
```

### Testing

Mock the HTTP client for unit tests:

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_get_quote():
    service = MyAPIService()
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"symbol": "AAPL", "price": 150.0}
    
    with patch.object(
        httpx.AsyncClient,
        "request",
        new_callable=AsyncMock,
        return_value=mock_response
    ):
        result = await service.get_quote("AAPL")
        assert result["symbol"] == "AAPL"
    
    await service.close()
```

## Implemented Services

The following services extend `BaseService`:

### Coming Soon

- **FinnhubService**: Real-time stock quotes and WebSocket feeds
- **CoinGeckoService**: Cryptocurrency data
- **YFinanceService**: Historical stock data
- **FMPService**: Company fundamentals and financial statements

## Architecture

```
services/
├── base.py              # BaseService abstract class + exceptions
├── __init__.py          # Exports base classes
├── finnhub_service.py   # Finnhub integration (coming soon)
├── coingecko_service.py # CoinGecko integration (coming soon)
├── yfinance_service.py  # yfinance integration (coming soon)
└── fmp_service.py       # FMP integration (coming soon)
```

## Best Practices

1. **Always use caching**: Specify `cache_type` and `cache_key_parts` for frequently accessed data
2. **Handle exceptions**: Catch specific exceptions (RateLimitError, AuthenticationError, etc.)
3. **Use context manager**: Prefer `async with service:` over manual `close()`
4. **Log appropriately**: The base service logs all requests, errors, and cache hits
5. **Test with mocks**: Mock `httpx.AsyncClient.request` in unit tests
6. **Respect rate limits**: The base service automatically handles rate limiting
7. **Set meaningful cache keys**: Use descriptive parts like `["quote", symbol]` not just `[symbol]`

## Rate Limiting

Rate limiting is automatic and per-service:

- Each service has independent rate limits
- Limits defined in `config.py` (default: 50 calls/minute)
- When rate limited, requests are denied and `RateLimitError` is raised
- After receiving 429 from API, service is automatically rate-limited for retry period

Check rate limit status:

```python
from utils.rate_limiter import rate_limiter

stats = rate_limiter.get_stats()
print(stats["myapi"]["calls_last_minute"])  # e.g., 12
print(stats["myapi"]["is_rate_limited"])    # False
```

## Caching

Caching is automatic when `cache_type` is specified:

1. First request: Cache miss → API call → Cache stored
2. Subsequent requests: Cache hit → Return cached data (no API call)
3. After TTL expires: Cache miss → New API call

Check cache status:

```python
from utils.cache import cache_manager

stats = cache_manager.get_stats()
print(stats["quotes"]["size"])     # e.g., 15 items
print(stats["quotes"]["ttl"])      # 60 seconds
```

## Logging

All service operations are logged using structured logging:

```json
{
  "event": "api_request",
  "service": "myapi",
  "method": "GET",
  "url": "https://api.myapi.com/v1/quote/AAPL",
  "attempt": 1,
  "timestamp": "2026-03-06T14:00:00Z"
}
```

Log levels:
- **DEBUG**: Cache hits, API calls
- **INFO**: Successful requests, service initialization
- **WARNING**: Rate limits, retries
- **ERROR**: Failed requests, authentication errors
