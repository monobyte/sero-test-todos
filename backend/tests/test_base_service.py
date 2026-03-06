"""
Tests for BaseService class.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

import httpx

from services.base import (
    BaseService,
    ServiceError,
    RateLimitError,
    AuthenticationError,
    NotFoundError,
    NetworkError,
    CacheType,
)
from utils import cache_manager, rate_limiter


class MockService(BaseService):
    """Mock service implementation for testing."""
    
    SERVICE_NAME = "mock_service"
    
    def _get_base_url(self) -> str:
        return "https://api.mock.com"
    
    def _get_api_key(self) -> str:
        return "test_api_key"


@pytest.fixture
def mock_service():
    """Create mock service instance."""
    return MockService()


@pytest.mark.asyncio
async def test_service_initialization(mock_service):
    """Test service initializes correctly."""
    assert mock_service.SERVICE_NAME == "mock_service"
    assert mock_service._get_base_url() == "https://api.mock.com"
    assert mock_service._get_api_key() == "test_api_key"
    assert mock_service._client is None


@pytest.mark.asyncio
async def test_get_client_creates_instance(mock_service):
    """Test HTTP client is created on first access."""
    client = await mock_service._get_client()
    assert isinstance(client, httpx.AsyncClient)
    assert mock_service._client is not None
    
    # Second call returns same instance
    client2 = await mock_service._get_client()
    assert client is client2
    
    await mock_service.close()


@pytest.mark.asyncio
async def test_close_cleanup(mock_service):
    """Test close properly cleans up resources."""
    await mock_service._get_client()
    assert mock_service._client is not None
    
    await mock_service.close()
    assert mock_service._client is None


@pytest.mark.asyncio
async def test_context_manager(mock_service):
    """Test async context manager behavior."""
    async with mock_service as service:
        assert service is mock_service
        client = await service._get_client()
        assert client is not None
    
    # After context exit, client should be closed
    assert mock_service._client is None


def test_build_cache_key(mock_service):
    """Test cache key building."""
    key = mock_service._build_cache_key("quote", "AAPL")
    assert key == "mock_service:quote:AAPL"
    
    key2 = mock_service._build_cache_key("historical", "BTC", "1d")
    assert key2 == "mock_service:historical:BTC:1d"


def test_cache_operations(mock_service):
    """Test cache get/set operations."""
    test_data = {"symbol": "AAPL", "price": 150.0}
    cache_key = mock_service._build_cache_key("quote", "AAPL")
    
    # Initially no cache
    result = mock_service._get_cached(CacheType.QUOTE, cache_key)
    assert result is None
    
    # Set cache
    mock_service._set_cached(CacheType.QUOTE, cache_key, test_data)
    
    # Retrieve from cache
    result = mock_service._get_cached(CacheType.QUOTE, cache_key)
    assert result == test_data


def test_rate_limit_check(mock_service):
    """Test rate limit checking."""
    # Should pass when rate limiter allows
    assert mock_service._check_rate_limit() is True
    
    # Should raise when rate limited
    rate_limiter.set_rate_limit("mock_service", 60)
    
    with pytest.raises(RateLimitError) as exc_info:
        mock_service._check_rate_limit()
    
    assert exc_info.value.service == "mock_service"
    assert exc_info.value.status_code == 429


def test_record_call(mock_service):
    """Test API call recording."""
    initial_count = len(rate_limiter.call_history.get("mock_service", []))
    
    mock_service._record_call()
    
    new_count = len(rate_limiter.call_history.get("mock_service", []))
    assert new_count == initial_count + 1


@pytest.mark.asyncio
async def test_make_request_success(mock_service):
    """Test successful API request."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": "test"}
    
    with patch.object(
        httpx.AsyncClient,
        "request",
        new_callable=AsyncMock,
        return_value=mock_response
    ):
        result = await mock_service._make_request("GET", "/test")
        assert result == {"data": "test"}
    
    await mock_service.close()


@pytest.mark.asyncio
async def test_make_request_with_cache(mock_service):
    """Test request uses cache when available."""
    # Set up cache
    cache_key = mock_service._build_cache_key("test")
    cached_data = {"cached": True}
    mock_service._set_cached(CacheType.QUOTE, cache_key, cached_data)
    
    # Should return cached data without making request
    result = await mock_service._make_request(
        "GET",
        "/test",
        cache_type=CacheType.QUOTE,
        cache_key_parts=["test"],
    )
    
    assert result == cached_data
    await mock_service.close()


@pytest.mark.asyncio
async def test_make_request_authentication_error(mock_service):
    """Test authentication error handling."""
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "401 Unauthorized",
        request=MagicMock(),
        response=mock_response
    )
    
    with patch.object(
        httpx.AsyncClient,
        "request",
        new_callable=AsyncMock,
        return_value=mock_response
    ):
        with pytest.raises(AuthenticationError) as exc_info:
            await mock_service._make_request("GET", "/test")
        
        assert exc_info.value.service == "mock_service"
        assert exc_info.value.status_code == 401
    
    await mock_service.close()


@pytest.mark.asyncio
async def test_make_request_not_found_error(mock_service):
    """Test not found error handling."""
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404 Not Found",
        request=MagicMock(),
        response=mock_response
    )
    
    with patch.object(
        httpx.AsyncClient,
        "request",
        new_callable=AsyncMock,
        return_value=mock_response
    ):
        with pytest.raises(NotFoundError) as exc_info:
            await mock_service._make_request("GET", "/test")
        
        assert exc_info.value.service == "mock_service"
        assert exc_info.value.status_code == 404
    
    await mock_service.close()


@pytest.mark.asyncio
async def test_make_request_rate_limit_error(mock_service):
    """Test rate limit error handling."""
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.headers = {"Retry-After": "60"}
    
    # Mock asyncio.sleep to avoid delays
    with patch("asyncio.sleep", new_callable=AsyncMock):
        # Mock to return 429 on all attempts
        with patch.object(
            httpx.AsyncClient,
            "request",
            new_callable=AsyncMock,
            return_value=mock_response
        ):
            with pytest.raises(RateLimitError) as exc_info:
                await mock_service._make_request("GET", "/test")
            
            assert exc_info.value.service == "mock_service"
            assert exc_info.value.retry_after == 60
    
    await mock_service.close()


@pytest.mark.asyncio
async def test_make_request_network_error(mock_service):
    """Test network error handling with retries."""
    # Mock asyncio.sleep to avoid delays
    with patch("asyncio.sleep", new_callable=AsyncMock):
        with patch.object(
            httpx.AsyncClient,
            "request",
            new_callable=AsyncMock,
            side_effect=httpx.NetworkError("Connection failed")
        ):
            with pytest.raises(NetworkError) as exc_info:
                await mock_service._make_request("GET", "/test")
            
            assert exc_info.value.service == "mock_service"
            assert "Connection failed" in str(exc_info.value.original_error)
    
    await mock_service.close()


@pytest.mark.asyncio
async def test_make_request_retry_on_server_error(mock_service):
    """Test retry logic on server errors."""
    # First two attempts fail with 503, third succeeds
    mock_response_fail = MagicMock()
    mock_response_fail.status_code = 503
    mock_response_fail.headers = {}
    
    mock_response_success = MagicMock()
    mock_response_success.status_code = 200
    mock_response_success.json.return_value = {"data": "success"}
    
    # Mock asyncio.sleep to avoid delays
    with patch("asyncio.sleep", new_callable=AsyncMock):
        with patch.object(
            httpx.AsyncClient,
            "request",
            new_callable=AsyncMock,
            side_effect=[
                mock_response_fail,
                mock_response_fail,
                mock_response_success,
            ]
        ):
            result = await mock_service._make_request("GET", "/test")
            assert result == {"data": "success"}
    
    await mock_service.close()


def test_parse_retry_after_header(mock_service):
    """Test Retry-After header parsing."""
    # Test integer value
    response = MagicMock()
    response.headers = {"Retry-After": "120"}
    assert mock_service._parse_retry_after(response) == 120
    
    # Test X-RateLimit-Reset timestamp
    future_timestamp = int(datetime.utcnow().timestamp()) + 90
    response.headers = {"X-RateLimit-Reset": str(future_timestamp)}
    retry = mock_service._parse_retry_after(response)
    assert 80 <= retry <= 100  # Should be around 90 seconds
    
    # Test default (no headers)
    response.headers = {}
    assert mock_service._parse_retry_after(response) == 60


def test_service_error_attributes():
    """Test ServiceError exception attributes."""
    error = ServiceError(
        message="Test error",
        service="test_service",
        status_code=500,
        response_data={"error": "details"}
    )
    
    assert error.message == "Test error"
    assert error.service == "test_service"
    assert error.status_code == 500
    assert error.response_data == {"error": "details"}


def test_rate_limit_error_message():
    """Test RateLimitError message formatting."""
    error = RateLimitError("test_service", retry_after=60)
    assert "Rate limit exceeded" in str(error)
    assert "Retry after 60s" in str(error)
    
    error2 = RateLimitError("test_service")
    assert "Rate limit exceeded" in str(error2)


def test_authentication_error_message():
    """Test AuthenticationError message formatting."""
    error = AuthenticationError("test_service")
    assert "Authentication failed" in str(error)
    assert "Check API key" in str(error)


def test_not_found_error_attributes():
    """Test NotFoundError attributes."""
    error = NotFoundError("test_service", "INVALID")
    assert error.resource == "INVALID"
    assert "not found" in str(error)
    assert error.status_code == 404
