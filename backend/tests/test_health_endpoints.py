"""
Integration tests for health check endpoints.

Tests the /health, /health/cache, and /health/rate-limits endpoints.
"""
import pytest
from fastapi import status
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestHealthEndpoints:
    """Integration tests for health check endpoints."""

    def test_health_check_returns_200(self, client: TestClient):
        """Test that health check endpoint returns 200 OK."""
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK

    def test_health_check_response_structure(self, client: TestClient):
        """Test that health check returns expected response structure."""
        response = client.get("/health")
        data = response.json()

        # Verify all required fields are present
        assert "status" in data
        assert "timestamp" in data
        assert "version" in data
        assert "environment" in data
        assert "services" in data

        # Verify field types
        assert isinstance(data["status"], str)
        assert isinstance(data["version"], str)
        assert isinstance(data["environment"], str)
        assert isinstance(data["services"], dict)

    def test_health_check_status_healthy(self, client: TestClient):
        """Test that health check reports healthy status."""
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"

    def test_health_check_version(self, client: TestClient):
        """Test that health check returns correct version."""
        response = client.get("/health")
        data = response.json()
        assert data["version"] == "0.1.0"

    def test_health_check_services_structure(self, client: TestClient):
        """Test that services status includes expected keys."""
        response = client.get("/health")
        data = response.json()
        services = data["services"]

        # Expected service keys
        expected_services = ["finnhub", "fmp", "alpha_vantage", "twelve_data", "coingecko"]
        
        for service in expected_services:
            assert service in services
            assert isinstance(services[service], bool)

    def test_health_check_with_api_keys(self, client: TestClient, mock_api_keys):
        """Test health check when API keys are configured."""
        response = client.get("/health")
        data = response.json()
        services = data["services"]

        # With mocked API keys, these should be True
        assert services["finnhub"] is True
        assert services["coingecko"] is True
        assert services["fmp"] is True

    def test_cache_stats_returns_200(self, client: TestClient):
        """Test that cache stats endpoint returns 200 OK."""
        response = client.get("/health/cache")
        assert response.status_code == status.HTTP_200_OK

    def test_cache_stats_response_structure(self, client: TestClient):
        """Test that cache stats returns expected structure."""
        response = client.get("/health/cache")
        data = response.json()

        # Verify cache types are present
        assert "quotes" in data
        assert "historical" in data
        assert "fundamentals" in data

        # Verify each cache has required fields
        for cache_type in ["quotes", "historical", "fundamentals"]:
            cache_data = data[cache_type]
            assert "size" in cache_data
            assert "maxsize" in cache_data
            assert "ttl" in cache_data
            
            # Verify types
            assert isinstance(cache_data["size"], int)
            assert isinstance(cache_data["maxsize"], int)
            assert isinstance(cache_data["ttl"], int)

    def test_cache_stats_initial_state(self, client: TestClient):
        """Test that cache stats show empty caches initially."""
        response = client.get("/health/cache")
        data = response.json()

        # All caches should be empty initially (autouse fixture clears them)
        assert data["quotes"]["size"] == 0
        assert data["historical"]["size"] == 0
        assert data["fundamentals"]["size"] == 0

    def test_rate_limit_stats_returns_200(self, client: TestClient):
        """Test that rate limit stats endpoint returns 200 OK."""
        response = client.get("/health/rate-limits")
        assert response.status_code == status.HTTP_200_OK

    def test_rate_limit_stats_response_structure(self, client: TestClient):
        """Test that rate limit stats returns dictionary."""
        response = client.get("/health/rate-limits")
        data = response.json()
        
        # Should return a dictionary (empty initially)
        assert isinstance(data, dict)

    def test_root_endpoint(self, client: TestClient):
        """Test root endpoint returns API information."""
        response = client.get("/")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert "message" in data
        assert "version" in data
        assert "docs" in data
        assert "health" in data
        
        assert data["docs"] == "/docs"
        assert data["health"] == "/health"

    def test_health_endpoints_cors_headers(self, client: TestClient):
        """Test that health endpoints include CORS headers."""
        response = client.get("/health")
        
        # CORS headers should be present
        assert "access-control-allow-origin" in response.headers
