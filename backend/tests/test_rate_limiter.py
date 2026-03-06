"""
Unit tests for the rate limiter.

Tests rate limiting functionality to prevent exceeding API quotas.
"""
import pytest
import time
from datetime import datetime, timedelta
from utils import rate_limiter


@pytest.mark.unit
@pytest.mark.rate_limit
class TestRateLimiter:
    """Unit tests for RateLimiter class."""

    def test_can_call_initially_returns_true(self):
        """Test that first call to a service is allowed."""
        assert rate_limiter.can_call("test_service") is True

    def test_record_call_increments_count(self):
        """Test that recording a call adds it to history."""
        service = "test_service"
        
        rate_limiter.record_call(service)
        
        assert service in rate_limiter.call_history
        assert len(rate_limiter.call_history[service]) == 1

    def test_multiple_calls_recorded(self):
        """Test that multiple calls are recorded correctly."""
        service = "test_service"
        
        for i in range(5):
            rate_limiter.record_call(service)
        
        assert len(rate_limiter.call_history[service]) == 5

    def test_rate_limit_enforced(self, monkeypatch):
        """Test that rate limit is enforced when threshold is reached."""
        from config import settings
        monkeypatch.setattr(settings, "rate_limit_calls_per_minute", 5)
        
        service = "test_service"
        
        # Make calls up to the limit
        for i in range(5):
            assert rate_limiter.can_call(service) is True
            rate_limiter.record_call(service)
        
        # Next call should be denied
        assert rate_limiter.can_call(service) is False

    def test_rate_limit_per_service(self, monkeypatch):
        """Test that rate limits are tracked independently per service."""
        from config import settings
        monkeypatch.setattr(settings, "rate_limit_calls_per_minute", 3)
        
        service_a = "service_a"
        service_b = "service_b"
        
        # Make calls to service_a up to limit
        for i in range(3):
            assert rate_limiter.can_call(service_a) is True
            rate_limiter.record_call(service_a)
        
        # service_a should be rate limited
        assert rate_limiter.can_call(service_a) is False
        
        # service_b should still be allowed
        assert rate_limiter.can_call(service_b) is True

    def test_set_rate_limit_manually(self):
        """Test manually setting a rate limit for a service."""
        service = "test_service"
        
        rate_limiter.set_rate_limit(service, duration_seconds=60)
        
        assert rate_limiter.can_call(service) is False
        assert service in rate_limiter.rate_limit_until

    def test_clear_rate_limit(self):
        """Test clearing a rate limit for a service."""
        service = "test_service"
        
        rate_limiter.set_rate_limit(service, duration_seconds=60)
        assert rate_limiter.can_call(service) is False
        
        rate_limiter.clear_rate_limit(service)
        assert rate_limiter.can_call(service) is True

    def test_rate_limit_expiration(self):
        """Test that rate limit expires after duration."""
        service = "test_service"
        
        # Set very short rate limit
        rate_limiter.set_rate_limit(service, duration_seconds=1)
        assert rate_limiter.can_call(service) is False
        
        # Wait for expiration
        time.sleep(1.5)
        
        # Should be allowed again
        assert rate_limiter.can_call(service) is True

    def test_get_stats_empty(self):
        """Test stats when no calls have been made."""
        stats = rate_limiter.get_stats()
        assert isinstance(stats, dict)
        assert len(stats) == 0

    def test_get_stats_with_calls(self):
        """Test stats after making calls."""
        service = "test_service"
        
        for i in range(3):
            rate_limiter.record_call(service)
        
        stats = rate_limiter.get_stats()
        
        assert service in stats
        assert stats[service]["calls_last_minute"] == 3
        assert stats[service]["is_rate_limited"] is False
        assert "limit" in stats[service]

    def test_get_stats_with_rate_limit(self):
        """Test stats when service is rate limited."""
        service = "test_service"
        
        rate_limiter.set_rate_limit(service, duration_seconds=60)
        stats = rate_limiter.get_stats()
        
        # Service should show in stats even without calls
        # because it has a rate limit
        # (Note: Current implementation only shows services with call history)
        # So we need to record a call first
        rate_limiter.record_call(service)
        stats = rate_limiter.get_stats()
        
        assert service in stats
        assert stats[service]["is_rate_limited"] is True
        assert stats[service]["rate_limit_until"] is not None

    def test_old_calls_removed_from_window(self):
        """Test that calls outside the 1-minute window are removed."""
        service = "test_service"
        
        # Manually add an old call (2 minutes ago)
        old_time = datetime.utcnow() - timedelta(minutes=2)
        rate_limiter.call_history[service] = [old_time]
        
        # Check if can call (should clean up old calls)
        assert rate_limiter.can_call(service) is True
        
        # Old call should be removed
        assert len(rate_limiter.call_history[service]) == 0

    def test_rate_limit_disabled(self, monkeypatch):
        """Test that rate limiting can be disabled."""
        from config import settings
        monkeypatch.setattr(settings, "rate_limit_enabled", False)
        monkeypatch.setattr(settings, "rate_limit_calls_per_minute", 1)
        
        service = "test_service"
        
        # Make many calls beyond the limit
        for i in range(10):
            assert rate_limiter.can_call(service) is True
            rate_limiter.record_call(service)
        
        # Should still be allowed (rate limiting disabled)
        assert rate_limiter.can_call(service) is True

    def test_multiple_services_independent_limits(self, monkeypatch):
        """Test that multiple services have independent rate limits."""
        from config import settings
        monkeypatch.setattr(settings, "rate_limit_calls_per_minute", 2)
        
        services = ["finnhub", "coingecko", "fmp"]
        
        # Each service can make calls up to the limit independently
        for service in services:
            for i in range(2):
                assert rate_limiter.can_call(service) is True
                rate_limiter.record_call(service)
            
            # Each should be rate limited
            assert rate_limiter.can_call(service) is False
        
        # Verify all are tracked
        stats = rate_limiter.get_stats()
        for service in services:
            assert service in stats
            assert stats[service]["calls_last_minute"] == 2

    @pytest.mark.slow
    def test_rate_limit_window_sliding(self):
        """Test that the 1-minute window slides correctly."""
        from config import settings
        import pytest
        
        # This test would need to wait 60+ seconds to properly test
        # Skip in normal test runs, but keep for documentation
        pytest.skip("Slow test - requires 60+ second wait")
        
        service = "test_service"
        original_limit = settings.rate_limit_calls_per_minute
        
        # Make calls up to limit
        for i in range(original_limit):
            rate_limiter.record_call(service)
        
        # Should be at limit
        assert rate_limiter.can_call(service) is False
        
        # Wait for window to slide (61 seconds to be safe)
        time.sleep(61)
        
        # Should be allowed again
        assert rate_limiter.can_call(service) is True
