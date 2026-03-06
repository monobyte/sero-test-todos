"""
In-memory caching with TTL support using cachetools.
Reduces API calls while keeping data reasonably fresh.

CACHING STRATEGY:
-----------------
The cache uses three separate TTLCache instances with different Time-To-Live (TTL)
values optimized for each data type's update frequency and importance:

1. QUOTES CACHE (TTL: 60 seconds)
   - Near-real-time stock/crypto prices
   - Short TTL balances freshness vs API call volume
   - For a stock updating every second, 60s TTL = 98% fewer API calls
   - Acceptable staleness: 1 minute is reasonable for personal monitoring
   - Example: AAPL quote cached at 14:00:00, expires at 14:01:00

2. HISTORICAL CACHE (TTL: 3600 seconds = 1 hour)
   - Daily OHLCV candles (open, high, low, close, volume)
   - Daily candles don't change after market close
   - Even intraday candles are stable once the interval completes
   - Longer TTL dramatically reduces historical API calls
   - Example: AAPL daily chart cached at 10:00:00, expires at 11:00:00

3. FUNDAMENTALS CACHE (TTL: 86400 seconds = 24 hours)
   - Company data: market cap, P/E ratio, dividend yield, etc.
   - Fundamental data changes infrequently (quarterly earnings, etc.)
   - Very long TTL minimizes calls to expensive fundamentals endpoints
   - Example: AAPL fundamentals cached at midnight, expires next midnight

CACHE SIZING:
-------------
- quotes_cache: 1000 items (typical use: 50-100 active symbols)
- historical_cache: 500 items (symbol+interval combos: AAPL_1d, AAPL_1h, etc.)
- fundamentals_cache: 200 items (fewer requests for fundamentals)

WHY IN-MEMORY:
--------------
- Fast: No network/disk I/O overhead
- Simple: No external dependencies (Redis, Memcached)
- Acceptable: For single-instance personal use, in-memory is sufficient
- Trade-off: Data lost on restart (acceptable for caching non-critical data)

PRODUCTION CONSIDERATIONS:
--------------------------
- For multi-instance deployments, use Redis for shared cache
- For data persistence, consider SQLite/PostgreSQL for historical data warehouse
- Monitor cache hit rates via /health/cache endpoint
- Adjust TTLs in .env based on your usage patterns and API quotas

RATE LIMIT PROTECTION:
----------------------
Caching directly reduces API calls, helping stay within free-tier limits:
- Finnhub: 60 calls/min → With 60s cache, 50+ users can share 1 API call
- CoinGecko: 10k calls/month → 60s cache reduces monthly calls by 98%
- FMP: 250 calls/day → 1h historical cache = ~6 calls/day for hourly checks

CACHE INVALIDATION:
-------------------
- Automatic: TTL expiration (cachetools handles this)
- Manual: clear_all() method or restart application
- No manual invalidation per-symbol (would add complexity)
- "There are only two hard things in Computer Science: cache invalidation
   and naming things." — Phil Karlton
"""
from datetime import datetime, timedelta
from typing import Any, Optional

from cachetools import TTLCache

from config import settings
from .logger import get_logger

logger = get_logger(__name__)


class CacheManager:
    """
    Manages multiple TTL caches for different data types.
    
    Separate caches with different TTLs:
    - Quotes: Short TTL (60s) for near-real-time data
    - Historical: Medium TTL (1h) for daily/intraday candles
    - Fundamentals: Long TTL (24h) for company data that changes rarely
    """

    def __init__(self) -> None:
        """Initialize cache manager with separate caches."""
        # Cache for real-time quotes (short TTL)
        self.quotes_cache = TTLCache(
            maxsize=1000, ttl=settings.cache_ttl_quotes
        )
        
        # Cache for historical data (medium TTL)
        self.historical_cache = TTLCache(
            maxsize=500, ttl=settings.cache_ttl_historical
        )
        
        # Cache for fundamentals (long TTL)
        self.fundamentals_cache = TTLCache(
            maxsize=200, ttl=settings.cache_ttl_fundamentals
        )
        
        logger.info(
            "cache_initialized",
            quotes_ttl=settings.cache_ttl_quotes,
            historical_ttl=settings.cache_ttl_historical,
            fundamentals_ttl=settings.cache_ttl_fundamentals,
        )

    def get_quote(self, key: str) -> Optional[Any]:
        """
        Get cached quote data.
        
        Args:
            key: Cache key (typically symbol)
            
        Returns:
            Cached data or None if not found/expired
        """
        value = self.quotes_cache.get(key)
        if value:
            logger.debug("cache_hit", cache_type="quotes", key=key)
        return value

    def set_quote(self, key: str, value: Any) -> None:
        """
        Cache quote data.
        
        Args:
            key: Cache key
            value: Data to cache
        """
        self.quotes_cache[key] = value
        logger.debug("cache_set", cache_type="quotes", key=key)

    def get_historical(self, key: str) -> Optional[Any]:
        """
        Get cached historical data.
        
        Args:
            key: Cache key (symbol + interval)
            
        Returns:
            Cached data or None if not found/expired
        """
        value = self.historical_cache.get(key)
        if value:
            logger.debug("cache_hit", cache_type="historical", key=key)
        return value

    def set_historical(self, key: str, value: Any) -> None:
        """
        Cache historical data.
        
        Args:
            key: Cache key
            value: Data to cache
        """
        self.historical_cache[key] = value
        logger.debug("cache_set", cache_type="historical", key=key)

    def get_fundamental(self, key: str) -> Optional[Any]:
        """
        Get cached fundamental data.
        
        Args:
            key: Cache key (typically symbol)
            
        Returns:
            Cached data or None if not found/expired
        """
        value = self.fundamentals_cache.get(key)
        if value:
            logger.debug("cache_hit", cache_type="fundamentals", key=key)
        return value

    def set_fundamental(self, key: str, value: Any) -> None:
        """
        Cache fundamental data.
        
        Args:
            key: Cache key
            value: Data to cache
        """
        self.fundamentals_cache[key] = value
        logger.debug("cache_set", cache_type="fundamentals", key=key)

    def clear_all(self) -> None:
        """Clear all caches."""
        self.quotes_cache.clear()
        self.historical_cache.clear()
        self.fundamentals_cache.clear()
        logger.info("cache_cleared")

    def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache sizes and hit rates
        """
        return {
            "quotes": {
                "size": len(self.quotes_cache),
                "maxsize": self.quotes_cache.maxsize,
                "ttl": settings.cache_ttl_quotes,
            },
            "historical": {
                "size": len(self.historical_cache),
                "maxsize": self.historical_cache.maxsize,
                "ttl": settings.cache_ttl_historical,
            },
            "fundamentals": {
                "size": len(self.fundamentals_cache),
                "maxsize": self.fundamentals_cache.maxsize,
                "ttl": settings.cache_ttl_fundamentals,
            },
        }


# Global cache manager instance
cache_manager = CacheManager()
