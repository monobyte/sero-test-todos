# API Provider Reference

Comprehensive guide to free-tier financial data APIs integrated in Market Monitor.

## Stock Data APIs

### 1. Finnhub (Primary - Stocks)

**Website:** https://finnhub.io

**Free Tier Limits (2026):**
- 60 API calls per minute
- Real-time US stock quotes via WebSocket
- Historical data (daily candles)
- Company news and sentiment

**Best For:**
- Real-time US stock quotes
- WebSocket live feeds
- News and sentiment analysis

**Endpoints:**
- Quote: `GET /quote?symbol=AAPL`
- Candles: `GET /stock/candle?symbol=AAPL&resolution=D&from=...&to=...`
- WebSocket: `wss://ws.finnhub.io?token=YOUR_TOKEN`

**Rate Limit Headers:**
```
X-Ratelimit-Limit: 60
X-Ratelimit-Remaining: 59
X-Ratelimit-Reset: 1646582400
```

**Error Codes:**
- 429: Rate limit exceeded
- 401: Invalid API key
- 404: Symbol not found

**Signup:** https://finnhub.io/register

---

### 2. Financial Modeling Prep (FMP)

**Website:** https://site.financialmodelingprep.com

**Free Tier Limits (2026):**
- 250 API calls per day
- Historical prices (up to 5 years)
- Financial statements
- Company profiles and fundamentals

**Best For:**
- Company fundamentals
- Financial statements (income, balance sheet, cash flow)
- Historical adjusted prices
- Key metrics (P/E, EPS, etc.)

**Endpoints:**
- Quote: `GET /v3/quote/AAPL?apikey=YOUR_KEY`
- Historical: `GET /v3/historical-price-full/AAPL?apikey=YOUR_KEY`
- Fundamentals: `GET /v3/profile/AAPL?apikey=YOUR_KEY`

**Signup:** https://site.financialmodelingprep.com/developer/docs

---

### 3. Alpha Vantage

**Website:** https://www.alphavantage.co

**Free Tier Limits (2026):**
- 25 API calls per day (very limited!)
- 5 API calls per minute

**Best For:**
- Technical indicators (RSI, MACD, SMA)
- Backup for fundamental data
- FX rates

**Endpoints:**
- Quote: `GET /query?function=GLOBAL_QUOTE&symbol=AAPL&apikey=YOUR_KEY`
- Intraday: `GET /query?function=TIME_SERIES_INTRADAY&symbol=AAPL&interval=5min`
- RSI: `GET /query?function=RSI&symbol=AAPL&interval=daily&time_period=14`

**Note:** Very limited free tier. Use sparingly as fallback only.

**Signup:** https://www.alphavantage.co/support/#api-key

---

### 4. Twelve Data

**Website:** https://twelvedata.com

**Free Tier Limits (2026):**
- 800 API calls per day
- 8 API calls per minute
- Real-time and historical data

**Best For:**
- Backup for stock data
- International markets
- Forex and commodities

**Endpoints:**
- Quote: `GET /quote?symbol=AAPL&apikey=YOUR_KEY`
- Time Series: `GET /time_series?symbol=AAPL&interval=1day&apikey=YOUR_KEY`

**Signup:** https://twelvedata.com/pricing

---

### 5. yfinance (No Key Required)

**Library:** Python package (not official API)

**Limits:**
- No official rate limits
- Can break when Yahoo changes HTML structure
- No API key required

**Best For:**
- Quick prototyping
- Historical adjusted data
- Fallback when other APIs fail

**Usage:**
```python
import yfinance as yf
ticker = yf.Ticker("AAPL")
hist = ticker.history(period="1mo")
info = ticker.info
```

**Pros:**
- Free, no signup
- Easy to use
- Adjusted historical data

**Cons:**
- Unofficial (scrapes Yahoo Finance)
- Can break at any time
- No guaranteed uptime
- No support

**Fallback Strategy:**
Use yfinance when:
1. Other APIs are rate limited
2. Quick development/testing
3. Non-critical data fetching

---

## Crypto Data APIs

### 1. CoinGecko (Primary - Crypto)

**Website:** https://www.coingecko.com/en/api

**Free Tier Limits (2026):**
- Demo tier: 30-50 calls per minute
- 10,000 calls per month
- No credit card required

**Coverage:**
- 18,000+ cryptocurrencies
- Real-time prices
- Historical OHLCV data
- Market cap, volume, rankings

**Best For:**
- Crypto prices and market data
- Historical OHLCV candles
- Market cap rankings
- Wide coin coverage

**Endpoints:**
- Price: `GET /v3/simple/price?ids=bitcoin&vs_currencies=usd`
- OHLC: `GET /v3/coins/bitcoin/ohlc?vs_currency=usd&days=30`
- Market Chart: `GET /v3/coins/bitcoin/market_chart?vs_currency=usd&days=30`

**Rate Limit Headers:**
```
X-Ratelimit-Limit: 50
X-Ratelimit-Remaining: 49
```

**Signup:** https://www.coingecko.com/en/api/pricing

---

### 2. Binance Public API (No Key Required)

**Website:** https://binance-docs.github.io/apidocs/spot/en

**Free Tier:**
- Public endpoints require no API key
- WebSocket for real-time klines/trades
- High rate limits (1200 requests/min)

**Best For:**
- Real-time crypto prices
- High-frequency data
- WebSocket live feeds
- Intraday klines (candlesticks)

**Endpoints:**
- Ticker: `GET /api/v3/ticker/price?symbol=BTCUSDT`
- Klines: `GET /api/v3/klines?symbol=BTCUSDT&interval=1h`
- WebSocket: `wss://stream.binance.com:9443/ws/btcusdt@kline_1m`

**Usage with CCXT:**
```python
import ccxt
exchange = ccxt.binance()
ticker = exchange.fetch_ticker('BTC/USDT')
ohlcv = exchange.fetch_ohlcv('BTC/USDT', '1h')
```

**Pros:**
- No API key for market data
- High rate limits
- WebSocket support
- Reliable uptime

**Cons:**
- Only coins listed on Binance
- Mainly BTC, ETH, major coins
- Less coverage than CoinGecko

---

### 3. Finnhub (Crypto Support)

**Free Tier:**
- Same 60 calls/min as stock data
- Crypto quotes and candles
- Limited to major pairs

**Endpoints:**
- Crypto Quote: `GET /crypto/quote?symbol=BINANCE:BTCUSDT`
- Crypto Candles: `GET /crypto/candle?symbol=BINANCE:BTCUSDT&resolution=D`

---

## Unified Data Libraries (Optional)

### OpenBB Platform

**Website:** https://openbb.co

**Community Tier (Free):**
- Unified interface over multiple APIs
- Bring your own API keys to extend limits
- Python library with standardized output

**Features:**
- Stocks, crypto, forex, macro data
- Technical indicators built-in
- Standardized data models

**Usage:**
```python
from openbb import obb
# Configure with your API keys
obb.user.credentials.finnhub_api_key = "YOUR_KEY"

# Unified interface
quotes = obb.equity.price.quote("AAPL")
crypto = obb.crypto.price.historical("BTC-USD")
```

**Pros:**
- Single interface for multiple sources
- Consistent data format
- Built-in technical indicators

**Cons:**
- Abstraction layer (less control)
- Still subject to underlying API limits
- Additional dependency

---

## Rate Limit Management Strategy

### Priority Hierarchy

**For Stock Quotes:**
1. Finnhub (60/min, real-time)
2. yfinance (unlimited, but unreliable)
3. FMP (250/day)
4. Twelve Data (800/day)

**For Crypto Quotes:**
1. CoinGecko (50/min, 10k/month)
2. Binance (public, 1200/min)
3. Finnhub (60/min)

**For Historical Data:**
1. yfinance (free, unlimited)
2. Finnhub (60/min)
3. FMP (250/day)

### Error Handling

```python
async def get_stock_quote(symbol: str) -> Quote:
    # Try primary source
    try:
        if rate_limiter.can_call("finnhub"):
            return await finnhub_service.get_quote(symbol)
    except RateLimitError:
        logger.warning("Finnhub rate limited")
    
    # Try fallback 1
    try:
        return await yfinance_service.get_quote(symbol)
    except Exception:
        logger.warning("yfinance failed")
    
    # Try fallback 2
    try:
        if rate_limiter.can_call("fmp"):
            return await fmp_service.get_quote(symbol)
    except Exception:
        logger.error("All sources failed")
    
    # Return cached data if available
    cached = cache_manager.get_quote(symbol)
    if cached:
        return cached
    
    # All failed
    raise DataUnavailableError("Unable to fetch quote")
```

---

## API Key Environment Variables

In `.env`, configure:

```env
# Primary stock source
FINNHUB_API_KEY=your_finnhub_key

# Backup stock sources
FMP_API_KEY=your_fmp_key
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key
TWELVE_DATA_API_KEY=your_twelve_data_key

# Primary crypto source
COINGECKO_API_KEY=your_coingecko_key

# No keys needed for:
# - yfinance (Python library)
# - Binance public API (market data)
```

---

## Cost Analysis (All Free Tiers)

| Provider | Daily Limit | Monthly Limit | Use Case |
|----------|-------------|---------------|----------|
| Finnhub | 86,400 calls | ~2.6M calls | Primary stocks, WebSocket |
| CoinGecko | 72,000 calls | 10,000 calls* | Primary crypto |
| FMP | 250 calls | 7,500 calls | Fundamentals |
| Alpha Vantage | 25 calls | 750 calls | Backup only |
| Twelve Data | 800 calls | 24,000 calls | Backup stocks |
| yfinance | Unlimited | Unlimited | Fallback (unreliable) |
| Binance | 1.7M calls | 51M calls | Crypto WebSocket |

*CoinGecko has 10k monthly limit OR per-minute limit, whichever hits first.

**Total Free Capacity (Conservative):**
- ~88,000 calls per day
- ~2.6M calls per month

With caching (60s for quotes), actual API usage will be much lower.

---

## Best Practices

### 1. Caching
- Cache quotes for 60s (reduces API calls by ~98%)
- Cache historical for 1h (daily data doesn't change)
- Cache fundamentals for 24h (rarely changes)

### 2. Rate Limiting
- Track calls per service
- Implement exponential backoff on errors
- Use fallback sources when rate limited

### 3. Error Handling
- Always have fallback sources
- Return cached data when all sources fail
- Log all API errors for monitoring

### 4. WebSocket Strategy
- Use Finnhub WS for US stocks (real-time)
- Use Binance WS for crypto (real-time)
- Fallback to polling if WebSocket fails

### 5. Monitoring
- Track API usage per service
- Alert when approaching limits
- Monitor error rates

---

## 2026 Status Check

Before implementing, verify:
- ✅ Finnhub free tier still available
- ✅ CoinGecko demo tier details
- ✅ yfinance still functional
- ⚠️ FMP free tier limit (was 250/day, may change)
- ⚠️ Alpha Vantage still 25/day limit

**Action:** Check provider websites for current free tier limits before production deployment.
