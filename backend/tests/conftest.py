"""
Pytest fixtures and configuration for Market Monitor tests.
"""
import pytest
from fastapi.testclient import TestClient
from typing import Generator

from main import app
from utils import cache_manager, rate_limiter


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """
    FastAPI test client fixture.
    
    Yields:
        TestClient instance for making requests to the API
    """
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def reset_cache():
    """
    Auto-fixture that clears cache before each test.
    Ensures test isolation.
    """
    cache_manager.clear_all()
    yield
    cache_manager.clear_all()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """
    Auto-fixture that resets rate limiter before each test.
    Ensures test isolation.
    """
    # Clear all rate limiting state
    rate_limiter.call_history.clear()
    rate_limiter.rate_limit_until.clear()
    yield


@pytest.fixture
def mock_api_keys(monkeypatch):
    """
    Fixture to mock API keys in settings.
    
    Args:
        monkeypatch: pytest monkeypatch fixture
    """
    from config import settings
    
    monkeypatch.setattr(settings, "finnhub_api_key", "test_finnhub_key")
    monkeypatch.setattr(settings, "coingecko_api_key", "test_coingecko_key")
    monkeypatch.setattr(settings, "fmp_api_key", "test_fmp_key")
    
    yield settings


@pytest.fixture
def sample_quote_data():
    """
    Fixture providing sample quote data for testing.
    
    Returns:
        Dictionary with sample quote data
    """
    return {
        "symbol": "AAPL",
        "price": 150.25,
        "change": 2.50,
        "change_percent": 1.69,
        "volume": 50000000,
        "timestamp": "2026-03-06T14:00:00Z",
    }


@pytest.fixture
def sample_historical_data():
    """
    Fixture providing sample historical data for testing.
    
    Returns:
        List of OHLCV candles
    """
    return [
        {
            "timestamp": "2026-03-01T00:00:00Z",
            "open": 148.50,
            "high": 151.00,
            "low": 147.80,
            "close": 150.25,
            "volume": 45000000,
        },
        {
            "timestamp": "2026-03-02T00:00:00Z",
            "open": 150.25,
            "high": 152.50,
            "low": 149.00,
            "close": 151.75,
            "volume": 52000000,
        },
    ]
