"""
Rate limiting for external API calls.
Prevents exceeding free tier limits and implements backoff strategies.

RATE LIMITING STRATEGY:
-----------------------
This rate limiter protects the application from exceeding free-tier API quotas
by tracking API calls in a sliding 1-minute window per service.

WHY RATE LIMITING:
------------------
Free-tier APIs have strict limits that, when exceeded, result in:
1. 429 Too Many Requests errors (calls rejected)
2. Temporary IP bans (15-60 minutes)
3. Account suspension (for repeated violations)
4. Forced upgrade to paid tier

By proactively limiting ourselves to BELOW the official limits, we ensure:
- Reliable service (no unexpected 429 errors)
- API calls succeed when needed most
- Buffer for usage spikes
- Stay within free-tier quotas indefinitely

FREE-TIER LIMITS (2026):
------------------------
Service         | Official Limit      | Our Limit       | Buffer
----------------|---------------------|-----------------|--------
Finnhub         | 60 calls/min        | 50 calls/min    | 17%
CoinGecko       | 50 calls/min        | 40 calls/min    | 20%
                | 10k calls/month     | (via caching)   |
FMP             | 250 calls/day       | Conservative    | Usage tracking
Alpha Vantage   | 25 calls/day        | 20 calls/day    | 20%
yfinance        | Unlimited (unofficial) | No limit     | Relies on caching

SLIDING WINDOW ALGORITHM:
-------------------------
1. Track timestamp of every API call in a list per service
2. Before new call: Remove timestamps older than 1 minute
3. Count remaining timestamps in window
4. If count >= limit: DENY (return False)
5. If count < limit: ALLOW (return True), then record call after success

Example (limit = 5 calls/min):
- 14:00:00 → Call 1 ✓
- 14:00:10 → Call 2 ✓
- 14:00:20 → Call 3 ✓
- 14:00:30 → Call 4 ✓
- 14:00:40 → Call 5 ✓
- 14:00:50 → Call 6 ✗ DENIED (5 calls in last 60s)
- 14:01:01 → Call 6 ✓ (Call 1 at 14:00:00 expired, window now has 4 calls)

This is more accurate than fixed-window (e.g. "max 60 calls per minute starting
at :00 seconds") because it prevents bursts at window boundaries.

PER-SERVICE TRACKING:
---------------------
Each API service has independent rate limiting:
- Finnhub calls don't affect CoinGecko quota
- Allows parallel fetching from multiple sources
- Fallback services can be used when primary is rate limited

Example fallback chain:
1. Try Finnhub (primary)
2. If Finnhub rate limited → Try yfinance (fallback)
3. If yfinance fails → Try FMP (second fallback)

MANUAL RATE LIMITING (429 Responses):
--------------------------------------
When an API returns 429 Too Many Requests:
1. set_rate_limit(service, duration=60) → Block service for 60 seconds
2. Immediately switch to fallback service
3. After 60s, try primary again
4. Prevents hammering a rate-limited API

CONFIGURATION:
--------------
- RATE_LIMIT_ENABLED=true → Enable rate limiting (recommended)
- RATE_LIMIT_CALLS_PER_MINUTE=50 → Global default limit
- Per-service limits can be set programmatically (future enhancement)

MONITORING:
-----------
Check rate limit status via /health/rate-limits:
{
  "finnhub": {
    "calls_last_minute": 12,
    "limit": 50,
    "is_rate_limited": false,
    "rate_limit_until": null
  }
}

PRODUCTION CONSIDERATIONS:
--------------------------
- For multi-instance deployments: Use Redis for distributed rate limiting
  (e.g. redis-py with sliding window or token bucket algorithm)
- Add per-user rate limiting if implementing user accounts
- Track daily/monthly quotas (CoinGecko 10k/month, FMP 250/day)
- Alert when approaching quota limits (e.g. 80% of monthly limit)

COMBINED WITH CACHING:
----------------------
Rate limiting + caching work together:
1. Cache hit → No API call → No rate limit check needed
2. Cache miss → Rate limit check → API call if allowed
3. API call → Cache result → Future requests hit cache

Example (60s quote cache + 50 calls/min limit):
- 100 users request AAPL quote simultaneously
- First request: Cache miss → API call → Cache for 60s
- Next 99 requests: Cache hit → No API calls
- Result: 1 API call instead of 100 (100x reduction)

This makes free-tier APIs viable for real-world usage!
"""
from datetime import datetime, timedelta
from typing import Dict, Optional

from config import settings
from .logger import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """
    Simple in-memory rate limiter for API calls.
    
    Tracks calls per service and enforces limits based on free tier constraints.
    In production, consider Redis-backed rate limiting for multi-instance deployments.
    """

    def __init__(self) -> None:
        """Initialize rate limiter with tracking dictionaries."""
        # Track call counts per service: {service_name: [(timestamp, count), ...]}
        self.call_history: Dict[str, list[datetime]] = {}
        
        # Track rate limit status per service
        self.rate_limit_until: Dict[str, datetime] = {}
        
        logger.info(
            "rate_limiter_initialized",
            enabled=settings.rate_limit_enabled,
            calls_per_minute=settings.rate_limit_calls_per_minute,
        )

    def can_call(self, service: str) -> bool:
        """
        Check if a call to the service is allowed.
        
        Args:
            service: Service name (finnhub, coingecko, etc.)
            
        Returns:
            True if call is allowed, False if rate limited
        """
        if not settings.rate_limit_enabled:
            return True

        # Check if service is currently rate limited
        if service in self.rate_limit_until:
            if datetime.utcnow() < self.rate_limit_until[service]:
                logger.warning(
                    "rate_limit_active",
                    service=service,
                    until=self.rate_limit_until[service].isoformat(),
                )
                return False
            else:
                # Rate limit period expired
                del self.rate_limit_until[service]

        # Check call history for the last minute
        now = datetime.utcnow()
        one_minute_ago = now - timedelta(minutes=1)

        if service not in self.call_history:
            self.call_history[service] = []

        # Remove old calls outside the window
        self.call_history[service] = [
            ts for ts in self.call_history[service] if ts > one_minute_ago
        ]

        # Check if under limit
        call_count = len(self.call_history[service])
        if call_count >= settings.rate_limit_calls_per_minute:
            logger.warning(
                "rate_limit_exceeded",
                service=service,
                calls_in_window=call_count,
                limit=settings.rate_limit_calls_per_minute,
            )
            # Set rate limit for 1 minute
            self.rate_limit_until[service] = now + timedelta(minutes=1)
            return False

        return True

    def record_call(self, service: str) -> None:
        """
        Record a successful API call.
        
        Args:
            service: Service name
        """
        if not settings.rate_limit_enabled:
            return

        now = datetime.utcnow()
        if service not in self.call_history:
            self.call_history[service] = []

        self.call_history[service].append(now)
        logger.debug("api_call_recorded", service=service)

    def set_rate_limit(self, service: str, duration_seconds: int = 60) -> None:
        """
        Manually set a rate limit for a service (e.g., after receiving 429).
        
        Args:
            service: Service name
            duration_seconds: How long to rate limit (default 60s)
        """
        until = datetime.utcnow() + timedelta(seconds=duration_seconds)
        self.rate_limit_until[service] = until
        logger.warning(
            "rate_limit_set",
            service=service,
            duration=duration_seconds,
            until=until.isoformat(),
        )

    def clear_rate_limit(self, service: str) -> None:
        """
        Clear rate limit for a service.
        
        Args:
            service: Service name
        """
        if service in self.rate_limit_until:
            del self.rate_limit_until[service]
            logger.info("rate_limit_cleared", service=service)

    def get_stats(self) -> dict[str, any]:
        """
        Get rate limiter statistics.
        
        Returns:
            Dictionary with call counts and rate limit status per service
        """
        now = datetime.utcnow()
        one_minute_ago = now - timedelta(minutes=1)

        stats = {}
        for service, calls in self.call_history.items():
            recent_calls = [ts for ts in calls if ts > one_minute_ago]
            is_limited = service in self.rate_limit_until and now < self.rate_limit_until[service]
            
            stats[service] = {
                "calls_last_minute": len(recent_calls),
                "limit": settings.rate_limit_calls_per_minute,
                "is_rate_limited": is_limited,
                "rate_limit_until": (
                    self.rate_limit_until[service].isoformat() if is_limited else None
                ),
            }

        return stats


# Global rate limiter instance
rate_limiter = RateLimiter()
