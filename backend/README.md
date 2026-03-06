# Market Monitor Backend

FastAPI-based backend for personal finance and trading research application.

## Features

- 🔄 Real-time stock and crypto price monitoring
- 📊 Historical market data with OHLCV candles
- 🔍 Trading idea generation and screening
- 🚀 WebSocket support for live price feeds
- 💾 Intelligent caching to minimize API calls
- ⚡ Rate limiting with free-tier protection
- 🛡️ Type-safe with Pydantic v2 models
- 📝 Structured logging with contextual information

## Architecture

```
backend/
├── main.py              # FastAPI application entry point
├── config.py            # Settings and environment variables
├── models/              # Pydantic data models
│   ├── base.py         # Common response models
│   └── market.py       # Market data models
├── routers/            # API route handlers
│   └── health.py       # Health check endpoints
├── services/           # External API integrations
│   ├── finnhub_service.py    # (future)
│   ├── coingecko_service.py  # (future)
│   └── yfinance_service.py   # (future)
└── utils/              # Utilities and helpers
    ├── cache.py        # Caching with TTL
    ├── rate_limiter.py # Rate limiting
    └── logger.py       # Structured logging
```

## Technology Stack

- **Framework**: FastAPI 0.109+ (async-first, automatic OpenAPI docs)
- **Server**: Uvicorn with standard extras (high-performance ASGI)
- **Validation**: Pydantic v2 (type-safe models)
- **HTTP Client**: httpx (async HTTP requests)
- **WebSockets**: websockets library
- **Caching**: cachetools (TTL-based in-memory cache)
- **Logging**: structlog (structured, contextual logging)

## Setup

### Prerequisites

- Python 3.11 or higher
- pip or uv package manager

### Installation

1. **Create virtual environment:**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   # Or with pyproject.toml:
   pip install -e .
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys (see below)
   ```

### API Keys (Free Tiers)

Sign up for free accounts and add keys to `.env`:

#### Stock Data
- **Finnhub** (Primary): https://finnhub.io/register
  - Free: ~60 calls/min, WebSocket real-time quotes
  - Add: `FINNHUB_API_KEY=your_key`

- **Financial Modeling Prep** (Fundamentals): https://site.financialmodelingprep.com/developer/docs
  - Free: 250 calls/day
  - Add: `FMP_API_KEY=your_key`

- **Alpha Vantage** (Backup): https://www.alphavantage.co/support/#api-key
  - Free: 25 calls/day
  - Add: `ALPHA_VANTAGE_API_KEY=your_key`

#### Crypto Data
- **CoinGecko** (Primary): https://www.coingecko.com/en/api/pricing
  - Demo tier: 30-50 calls/min, 10k calls/month
  - Add: `COINGECKO_API_KEY=your_key`

#### Notes
- **yfinance**: No API key required (scrapes Yahoo Finance)
- **Binance**: Public API endpoints need no key for market data

## Running the Server

### Development Mode (with auto-reload)
```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Production Mode
```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Using Python directly
```bash
cd backend
python main.py
```

The API will be available at:
- **API**: http://0.0.0.0:8000
- **Interactive Docs**: http://0.0.0.0:8000/docs
- **ReDoc**: http://0.0.0.0:8000/redoc
- **Health Check**: http://0.0.0.0:8000/health

## API Endpoints

### Current Endpoints

#### Health & Status
- `GET /health` - Service health check
- `GET /health/cache` - Cache statistics
- `GET /health/rate-limits` - Rate limit status

#### Root
- `GET /` - API information

### Future Endpoints (Planned)
- `GET /api/quotes/{symbol}` - Get real-time quote
- `GET /api/historical/{symbol}` - Get historical OHLCV data
- `GET /api/screener` - Screen stocks/crypto by criteria
- `WS /ws/quotes` - WebSocket for live price feeds

## Configuration

All configuration is managed through environment variables in `.env`:

### Application Settings
```env
APP_ENV=development          # development | production
APP_HOST=0.0.0.0            # Server bind address
APP_PORT=8000               # Server port
LOG_LEVEL=INFO              # DEBUG | INFO | WARNING | ERROR
```

### CORS Settings
```env
CORS_ORIGINS=http://localhost:3000,http://192.168.64.15:3000
```

### Cache Settings
```env
CACHE_TTL_QUOTES=60         # Quote cache TTL (seconds)
CACHE_TTL_HISTORICAL=3600   # Historical cache TTL (seconds)
CACHE_TTL_FUNDAMENTALS=86400 # Fundamental cache TTL (seconds)
```

### Rate Limiting
```env
RATE_LIMIT_ENABLED=true
RATE_LIMIT_CALLS_PER_MINUTE=50
```

## Rate Limiting & Caching Strategy

### Rate Limiting
- **Per-service tracking**: Separate limits for Finnhub, CoinGecko, etc.
- **Free-tier protection**: Prevents exceeding API quotas
- **Automatic backoff**: Implements retry delays on 429 errors
- **Fallback logic**: Switches to backup sources when limits hit

### Caching Strategy
- **Quotes**: 60s TTL (near-real-time without hammering APIs)
- **Historical**: 1h TTL (daily candles don't change frequently)
- **Fundamentals**: 24h TTL (company data rarely changes)
- **In-memory**: cachetools TTLCache (fast, no external dependencies)

### 2026 Known Limitations
- **yfinance**: No official API, can break when Yahoo changes HTML
  - Fallback: Use Finnhub or FMP for historical data
- **Free tier rate limits**: Monitor usage to avoid hitting caps
  - Finnhub: 60 calls/min
  - CoinGecko: 10k calls/month
  - FMP: 250 calls/day
- **No real-time crypto WebSocket**: Unless using Binance direct
  - Fallback: Polling CoinGecko every 1-5 minutes

## Development

### Project Structure Guidelines
- **models/**: Pydantic models for request/response validation
- **routers/**: FastAPI route handlers (thin layer, delegate to services)
- **services/**: Business logic and external API integrations
- **utils/**: Reusable utilities (cache, rate limiter, logger)

### Adding a New Data Source
1. Create service in `services/` (e.g., `new_service.py`)
2. Implement client with error handling and rate limiting
3. Add fallback logic in service layer
4. Create router in `routers/` for new endpoints
5. Register router in `main.py`

### Logging
Uses `structlog` for structured, contextual logging:
```python
from utils import get_logger

logger = get_logger(__name__)
logger.info("event_name", key1="value1", key2="value2")
```

### Error Handling
All endpoints return standard error responses:
```json
{
  "error": "RateLimitExceeded",
  "message": "API rate limit exceeded",
  "detail": {"retry_after": 60},
  "timestamp": "2026-03-06T14:00:00Z"
}
```

## Testing

(To be implemented)

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html
```

## Deployment

### Docker (Future)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Environment Variables in Production
- Set `APP_ENV=production`
- Use secrets management for API keys (not .env files)
- Enable HTTPS with reverse proxy (nginx, Caddy)
- Set appropriate `CORS_ORIGINS`

## License

Personal use only. Not for commercial redistribution.
All financial data is subject to respective API providers' terms of service.
