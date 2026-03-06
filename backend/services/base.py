"""
Base service class for external API integrations.

Provides common patterns for all service implementations:
- HTTP client management with httpx
- Caching integration (cache_manager)
- Rate limiting (rate_limiter)
- Error handling with structured logging
- Retry logic with exponential backoff
- Request/response logging
"""
import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional, TypeVar, Generic
from enum import Enum

import httpx
from pydantic import BaseModel

from config import settings
from utils.cache import cache_manager
from utils.rate_limiter import rate_limiter
from utils.logger import get_logger

logger = get_logger(__name__)

# Type variable for generic response types
T = TypeVar('T', bound=BaseModel)


class ServiceError(Exception):
    """Base exception for service errors."""
    
    def __init__(
        self,
        message: str,
        service: str,
        status_code: Optional[int] = None,
        response_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize service error.
        
        Args:
            message: Error message
            service: Service name (finnhub, coingecko, etc.)
            status_code: HTTP status code if applicable
            response_data: Response data from API if available
        """
        super().__init__(message)
        self.message = message
        self.service = service
        self.status_code = status_code
        self.response_data = response_data


class RateLimitError(ServiceError):
    """Raised when rate limit is exceeded."""
    
    def __init__(
        self,
        service: str,
        retry_after: Optional[int] = None,
        message: Optional[str] = None,
    ):
        """
        Initialize rate limit error.
        
        Args:
            service: Service name
            retry_after: Seconds until retry is allowed
            message: Custom error message
        """
        msg = message or f"Rate limit exceeded for {service}"
        if retry_after:
            msg += f". Retry after {retry_after}s"
        super().__init__(msg, service, status_code=429)
        self.retry_after = retry_after


class AuthenticationError(ServiceError):
    """Raised when API authentication fails."""
    
    def __init__(self, service: str, message: Optional[str] = None):
        """
        Initialize authentication error.
        
        Args:
            service: Service name
            message: Custom error message
        """
        msg = message or f"Authentication failed for {service}. Check API key."
        super().__init__(msg, service, status_code=401)


class NotFoundError(ServiceError):
    """Raised when requested resource is not found."""
    
    def __init__(self, service: str, resource: str, message: Optional[str] = None):
        """
        Initialize not found error.
        
        Args:
            service: Service name
            resource: Resource identifier (symbol, endpoint, etc.)
            message: Custom error message
        """
        msg = message or f"Resource '{resource}' not found in {service}"
        super().__init__(msg, service, status_code=404)
        self.resource = resource


class NetworkError(ServiceError):
    """Raised when network/connection error occurs."""
    
    def __init__(self, service: str, original_error: Exception):
        """
        Initialize network error.
        
        Args:
            service: Service name
            original_error: Original exception that caused the error
        """
        msg = f"Network error for {service}: {str(original_error)}"
        super().__init__(msg, service)
        self.original_error = original_error


class CacheType(str, Enum):
    """Cache type enumeration for different data categories."""
    
    QUOTE = "quote"
    HISTORICAL = "historical"
    FUNDAMENTAL = "fundamental"


class BaseService(ABC):
    """
    Abstract base class for external API service integrations.
    
    Provides common functionality:
    - HTTP client with timeout and retry configuration
    - Automatic caching with appropriate TTLs
    - Rate limiting to stay within free-tier quotas
    - Error handling and logging
    - Retry logic with exponential backoff
    
    Subclasses must implement:
    - SERVICE_NAME: Unique service identifier
    - _get_base_url(): Return API base URL
    - _get_api_key(): Return API key from settings
    """
    
    # Subclasses must define these
    SERVICE_NAME: str = "base"
    
    # Default retry configuration
    MAX_RETRIES: int = 3
    RETRY_BACKOFF_FACTOR: float = 2.0  # Exponential backoff: 1s, 2s, 4s
    RETRY_STATUSES: set[int] = {429, 500, 502, 503, 504}  # Retry on these status codes
    
    # Default timeout configuration (in seconds)
    REQUEST_TIMEOUT: float = 30.0
    
    def __init__(self):
        """Initialize base service with HTTP client."""
        self._client: Optional[httpx.AsyncClient] = None
        self._logger = get_logger(f"services.{self.SERVICE_NAME}")
    
    async def _get_client(self) -> httpx.AsyncClient:
        """
        Get or create HTTP client.
        
        Returns:
            Configured httpx AsyncClient
        """
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.REQUEST_TIMEOUT,
                headers=self._get_default_headers(),
                follow_redirects=True,
            )
        return self._client
    
    async def close(self) -> None:
        """Close HTTP client and cleanup resources."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            self._logger.info("service_closed", service=self.SERVICE_NAME)
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    @abstractmethod
    def _get_base_url(self) -> str:
        """
        Get API base URL.
        
        Returns:
            Base URL for API requests
        """
        pass
    
    @abstractmethod
    def _get_api_key(self) -> str:
        """
        Get API key from settings.
        
        Returns:
            API key for authentication
        """
        pass
    
    def _get_default_headers(self) -> Dict[str, str]:
        """
        Get default HTTP headers.
        
        Subclasses can override to add custom headers.
        
        Returns:
            Dictionary of HTTP headers
        """
        return {
            "User-Agent": "MarketMonitor/0.1.0",
            "Accept": "application/json",
        }
    
    def _check_rate_limit(self) -> bool:
        """
        Check if service is rate limited.
        
        Returns:
            True if request can proceed, False if rate limited
            
        Raises:
            RateLimitError: If service is currently rate limited
        """
        if not rate_limiter.can_call(self.SERVICE_NAME):
            self._logger.warning(
                "rate_limit_blocked",
                service=self.SERVICE_NAME,
            )
            raise RateLimitError(self.SERVICE_NAME)
        return True
    
    def _record_call(self) -> None:
        """Record successful API call for rate limiting."""
        rate_limiter.record_call(self.SERVICE_NAME)
    
    def _build_cache_key(self, *parts: str) -> str:
        """
        Build cache key from parts.
        
        Args:
            *parts: Key components (service, endpoint, symbol, params, etc.)
            
        Returns:
            Cache key string
        """
        return ":".join([self.SERVICE_NAME] + list(parts))
    
    def _get_cached(self, cache_type: CacheType, key: str) -> Optional[Any]:
        """
        Get data from cache.
        
        Args:
            cache_type: Type of cache to use
            key: Cache key
            
        Returns:
            Cached data or None if not found/expired
        """
        if cache_type == CacheType.QUOTE:
            return cache_manager.get_quote(key)
        elif cache_type == CacheType.HISTORICAL:
            return cache_manager.get_historical(key)
        elif cache_type == CacheType.FUNDAMENTAL:
            return cache_manager.get_fundamental(key)
        return None
    
    def _set_cached(self, cache_type: CacheType, key: str, value: Any) -> None:
        """
        Store data in cache.
        
        Args:
            cache_type: Type of cache to use
            key: Cache key
            value: Data to cache
        """
        if cache_type == CacheType.QUOTE:
            cache_manager.set_quote(key, value)
        elif cache_type == CacheType.HISTORICAL:
            cache_manager.set_historical(key, value)
        elif cache_type == CacheType.FUNDAMENTAL:
            cache_manager.set_fundamental(key, value)
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        cache_type: Optional[CacheType] = None,
        cache_key_parts: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        """
        Make HTTP request with caching, rate limiting, and retry logic.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            json_data: JSON request body
            headers: Additional headers
            cache_type: Type of cache to use (None to skip caching)
            cache_key_parts: Parts to build cache key (required if cache_type is set)
            
        Returns:
            Response data as dictionary
            
        Raises:
            RateLimitError: If rate limited
            AuthenticationError: If authentication fails
            NotFoundError: If resource not found
            NetworkError: If network error occurs
            ServiceError: For other API errors
        """
        # Check cache first
        if cache_type and cache_key_parts:
            cache_key = self._build_cache_key(*cache_key_parts)
            cached = self._get_cached(cache_type, cache_key)
            if cached is not None:
                self._logger.debug(
                    "cache_hit",
                    service=self.SERVICE_NAME,
                    cache_type=cache_type.value,
                    cache_key=cache_key,
                )
                return cached
        
        # Check rate limit
        self._check_rate_limit()
        
        # Build full URL
        url = f"{self._get_base_url()}{endpoint}"
        
        # Merge headers
        request_headers = self._get_default_headers()
        if headers:
            request_headers.update(headers)
        
        # Retry loop with exponential backoff
        last_error: Optional[Exception] = None
        for attempt in range(self.MAX_RETRIES):
            try:
                client = await self._get_client()
                
                self._logger.debug(
                    "api_request",
                    service=self.SERVICE_NAME,
                    method=method,
                    url=url,
                    attempt=attempt + 1,
                )
                
                response = await client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                    headers=request_headers,
                )
                
                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = self._parse_retry_after(response)
                    rate_limiter.set_rate_limit(self.SERVICE_NAME, retry_after)
                    
                    self._logger.warning(
                        "rate_limit_received",
                        service=self.SERVICE_NAME,
                        retry_after=retry_after,
                    )
                    
                    # Retry if we have attempts left
                    if attempt < self.MAX_RETRIES - 1:
                        await asyncio.sleep(retry_after)
                        continue
                    
                    raise RateLimitError(self.SERVICE_NAME, retry_after=retry_after)
                
                # Handle authentication errors
                if response.status_code == 401:
                    self._logger.error(
                        "authentication_failed",
                        service=self.SERVICE_NAME,
                        status_code=401,
                    )
                    raise AuthenticationError(self.SERVICE_NAME)
                
                # Handle not found
                if response.status_code == 404:
                    self._logger.warning(
                        "resource_not_found",
                        service=self.SERVICE_NAME,
                        url=url,
                    )
                    raise NotFoundError(self.SERVICE_NAME, endpoint)
                
                # Retry on server errors
                if response.status_code in self.RETRY_STATUSES:
                    self._logger.warning(
                        "retryable_error",
                        service=self.SERVICE_NAME,
                        status_code=response.status_code,
                        attempt=attempt + 1,
                    )
                    
                    if attempt < self.MAX_RETRIES - 1:
                        backoff = self.RETRY_BACKOFF_FACTOR ** attempt
                        await asyncio.sleep(backoff)
                        continue
                
                # Raise for other HTTP errors
                response.raise_for_status()
                
                # Record successful call
                self._record_call()
                
                # Parse response
                data = response.json()
                
                self._logger.info(
                    "api_success",
                    service=self.SERVICE_NAME,
                    method=method,
                    endpoint=endpoint,
                    status_code=response.status_code,
                )
                
                # Cache response if configured
                if cache_type and cache_key_parts:
                    cache_key = self._build_cache_key(*cache_key_parts)
                    self._set_cached(cache_type, cache_key, data)
                    self._logger.debug(
                        "response_cached",
                        service=self.SERVICE_NAME,
                        cache_type=cache_type.value,
                        cache_key=cache_key,
                    )
                
                return data
                
            except httpx.TimeoutException as e:
                last_error = e
                self._logger.warning(
                    "request_timeout",
                    service=self.SERVICE_NAME,
                    attempt=attempt + 1,
                    error=str(e),
                )
                
                if attempt < self.MAX_RETRIES - 1:
                    backoff = self.RETRY_BACKOFF_FACTOR ** attempt
                    await asyncio.sleep(backoff)
                    continue
                
            except httpx.NetworkError as e:
                last_error = e
                self._logger.warning(
                    "network_error",
                    service=self.SERVICE_NAME,
                    attempt=attempt + 1,
                    error=str(e),
                )
                
                if attempt < self.MAX_RETRIES - 1:
                    backoff = self.RETRY_BACKOFF_FACTOR ** attempt
                    await asyncio.sleep(backoff)
                    continue
                
            except (RateLimitError, AuthenticationError, NotFoundError):
                # Don't retry these errors
                raise
                
            except httpx.HTTPStatusError as e:
                last_error = e
                self._logger.error(
                    "http_error",
                    service=self.SERVICE_NAME,
                    status_code=e.response.status_code,
                    error=str(e),
                )
                
                # Don't retry client errors (4xx except 429)
                if 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                    raise ServiceError(
                        message=f"HTTP {e.response.status_code}: {str(e)}",
                        service=self.SERVICE_NAME,
                        status_code=e.response.status_code,
                    )
                
                # Retry server errors
                if attempt < self.MAX_RETRIES - 1:
                    backoff = self.RETRY_BACKOFF_FACTOR ** attempt
                    await asyncio.sleep(backoff)
                    continue
        
        # All retries exhausted
        self._logger.error(
            "max_retries_exceeded",
            service=self.SERVICE_NAME,
            attempts=self.MAX_RETRIES,
        )
        
        if isinstance(last_error, (httpx.TimeoutException, httpx.NetworkError)):
            raise NetworkError(self.SERVICE_NAME, last_error)
        
        raise ServiceError(
            message=f"Request failed after {self.MAX_RETRIES} attempts",
            service=self.SERVICE_NAME,
        )
    
    def _parse_retry_after(self, response: httpx.Response) -> int:
        """
        Parse Retry-After header from response.
        
        Args:
            response: HTTP response
            
        Returns:
            Seconds to wait before retrying (default 60)
        """
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return int(retry_after)
            except ValueError:
                # Retry-After can be a date, but we'll just use default
                pass
        
        # Check for X-RateLimit-Reset (Unix timestamp)
        reset_timestamp = response.headers.get("X-RateLimit-Reset")
        if reset_timestamp:
            try:
                reset_time = int(reset_timestamp)
                now = int(datetime.utcnow().timestamp())
                wait_time = max(0, reset_time - now)
                return min(wait_time, 300)  # Cap at 5 minutes
            except ValueError:
                pass
        
        # Default to 60 seconds
        return 60
