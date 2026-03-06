"""
Unit tests for the cache manager.

Tests caching functionality with TTL support for quotes, historical, and fundamental data.
"""
import pytest
import time
from utils import cache_manager


@pytest.mark.unit
@pytest.mark.cache
class TestCacheManager:
    """Unit tests for CacheManager class."""

    def test_quote_cache_set_and_get(self):
        """Test setting and getting quote data from cache."""
        key = "AAPL"
        value = {"price": 150.25, "volume": 50000000}
        
        cache_manager.set_quote(key, value)
        cached_value = cache_manager.get_quote(key)
        
        assert cached_value == value

    def test_quote_cache_miss(self):
        """Test that getting non-existent key returns None."""
        cached_value = cache_manager.get_quote("NONEXISTENT")
        assert cached_value is None

    def test_historical_cache_set_and_get(self):
        """Test setting and getting historical data from cache."""
        key = "AAPL_1d"
        value = [
            {"open": 148.50, "high": 151.00, "low": 147.80, "close": 150.25},
            {"open": 150.25, "high": 152.50, "low": 149.00, "close": 151.75},
        ]
        
        cache_manager.set_historical(key, value)
        cached_value = cache_manager.get_historical(key)
        
        assert cached_value == value

    def test_historical_cache_miss(self):
        """Test that getting non-existent historical key returns None."""
        cached_value = cache_manager.get_historical("NONEXISTENT_1d")
        assert cached_value is None

    def test_fundamental_cache_set_and_get(self):
        """Test setting and getting fundamental data from cache."""
        key = "AAPL_fundamentals"
        value = {
            "company_name": "Apple Inc.",
            "market_cap": 2500000000000,
            "pe_ratio": 28.5,
        }
        
        cache_manager.set_fundamental(key, value)
        cached_value = cache_manager.get_fundamental(key)
        
        assert cached_value == value

    def test_fundamental_cache_miss(self):
        """Test that getting non-existent fundamental key returns None."""
        cached_value = cache_manager.get_fundamental("NONEXISTENT_fundamentals")
        assert cached_value is None

    def test_cache_overwrite(self):
        """Test that setting the same key overwrites the previous value."""
        key = "AAPL"
        value1 = {"price": 150.25}
        value2 = {"price": 151.50}
        
        cache_manager.set_quote(key, value1)
        cache_manager.set_quote(key, value2)
        
        cached_value = cache_manager.get_quote(key)
        assert cached_value == value2

    def test_clear_all_caches(self):
        """Test that clear_all() removes all cached data."""
        cache_manager.set_quote("AAPL", {"price": 150.25})
        cache_manager.set_historical("AAPL_1d", [{"close": 150.25}])
        cache_manager.set_fundamental("AAPL_fundamentals", {"pe_ratio": 28.5})
        
        cache_manager.clear_all()
        
        assert cache_manager.get_quote("AAPL") is None
        assert cache_manager.get_historical("AAPL_1d") is None
        assert cache_manager.get_fundamental("AAPL_fundamentals") is None

    def test_cache_stats(self):
        """Test that get_stats() returns accurate cache statistics."""
        # Add some data to caches
        cache_manager.set_quote("AAPL", {"price": 150.25})
        cache_manager.set_quote("GOOGL", {"price": 2800.00})
        cache_manager.set_historical("AAPL_1d", [{"close": 150.25}])
        
        stats = cache_manager.get_stats()
        
        # Verify structure
        assert "quotes" in stats
        assert "historical" in stats
        assert "fundamentals" in stats
        
        # Verify quotes cache stats
        assert stats["quotes"]["size"] == 2
        assert stats["quotes"]["maxsize"] == 1000
        assert stats["quotes"]["ttl"] > 0
        
        # Verify historical cache stats
        assert stats["historical"]["size"] == 1
        assert stats["historical"]["maxsize"] == 500
        assert stats["historical"]["ttl"] > 0
        
        # Verify fundamentals cache stats
        assert stats["fundamentals"]["size"] == 0
        assert stats["fundamentals"]["maxsize"] == 200
        assert stats["fundamentals"]["ttl"] > 0

    def test_cache_stats_empty(self):
        """Test cache stats when all caches are empty."""
        cache_manager.clear_all()
        stats = cache_manager.get_stats()
        
        assert stats["quotes"]["size"] == 0
        assert stats["historical"]["size"] == 0
        assert stats["fundamentals"]["size"] == 0

    def test_multiple_cache_types_independent(self):
        """Test that different cache types are independent."""
        key = "AAPL"
        
        cache_manager.set_quote(key, {"type": "quote"})
        cache_manager.set_historical(key, {"type": "historical"})
        cache_manager.set_fundamental(key, {"type": "fundamental"})
        
        # Each cache should have its own value
        assert cache_manager.get_quote(key) == {"type": "quote"}
        assert cache_manager.get_historical(key) == {"type": "historical"}
        assert cache_manager.get_fundamental(key) == {"type": "fundamental"}

    @pytest.mark.slow
    def test_cache_ttl_expiration(self, monkeypatch):
        """
        Test that cache entries expire after TTL.
        
        Note: This test requires modifying TTL to a very short duration.
        In production, TTLs are 60s, 3600s, and 86400s.
        """
        # Temporarily set very short TTL for testing
        from config import settings
        monkeypatch.setattr(settings, "cache_ttl_quotes", 1)
        
        # Recreate cache manager with new TTL
        from utils.cache import CacheManager
        temp_cache = CacheManager()
        
        key = "TEST"
        value = {"price": 100.00}
        
        temp_cache.set_quote(key, value)
        assert temp_cache.get_quote(key) == value
        
        # Wait for TTL to expire
        time.sleep(1.5)
        
        # Should return None after expiration
        assert temp_cache.get_quote(key) is None

    def test_cache_complex_data_types(self):
        """Test caching complex nested data structures."""
        complex_data = {
            "symbol": "AAPL",
            "data": {
                "prices": [150.25, 151.50, 149.80],
                "volumes": [50000000, 52000000, 48000000],
                "metadata": {
                    "exchange": "NASDAQ",
                    "currency": "USD",
                    "last_updated": "2026-03-06T14:00:00Z",
                },
            },
        }
        
        cache_manager.set_quote("COMPLEX", complex_data)
        cached_value = cache_manager.get_quote("COMPLEX")
        
        assert cached_value == complex_data
        assert cached_value["data"]["metadata"]["exchange"] == "NASDAQ"
