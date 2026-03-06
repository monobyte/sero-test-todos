"""
Unit tests for Pydantic models.

Tests validation and serialization of API request/response models.
"""
import pytest
from datetime import datetime
from pydantic import ValidationError

from models import HealthCheck, ErrorResponse, SuccessResponse


@pytest.mark.unit
class TestHealthCheckModel:
    """Tests for HealthCheck model."""

    def test_health_check_valid_data(self):
        """Test creating HealthCheck with valid data."""
        data = {
            "status": "healthy",
            "timestamp": datetime.utcnow(),
            "version": "0.1.0",
            "environment": "development",
            "services": {"finnhub": True, "coingecko": True},
        }
        
        health_check = HealthCheck(**data)
        
        assert health_check.status == "healthy"
        assert health_check.version == "0.1.0"
        assert health_check.environment == "development"
        assert health_check.services["finnhub"] is True

    def test_health_check_default_timestamp(self):
        """Test that timestamp is auto-generated if not provided."""
        data = {
            "status": "healthy",
            "version": "0.1.0",
            "environment": "production",
            "services": {},
        }
        
        health_check = HealthCheck(**data)
        
        assert isinstance(health_check.timestamp, datetime)

    def test_health_check_serialization(self):
        """Test serializing HealthCheck to dict."""
        health_check = HealthCheck(
            status="healthy",
            version="0.1.0",
            environment="development",
            services={"test": True},
        )
        
        data = health_check.model_dump()
        
        assert data["status"] == "healthy"
        assert data["version"] == "0.1.0"
        assert "timestamp" in data
        assert isinstance(data["services"], dict)

    def test_health_check_json_serialization(self):
        """Test serializing HealthCheck to JSON."""
        health_check = HealthCheck(
            status="healthy",
            version="0.1.0",
            environment="development",
            services={"test": True},
        )
        
        json_str = health_check.model_dump_json()
        
        assert isinstance(json_str, str)
        assert "healthy" in json_str
        assert "0.1.0" in json_str


@pytest.mark.unit
class TestErrorResponseModel:
    """Tests for ErrorResponse model."""

    def test_error_response_valid_data(self):
        """Test creating ErrorResponse with valid data."""
        data = {
            "error": "ValidationError",
            "message": "Invalid input",
            "detail": {"field": "symbol", "issue": "required"},
        }
        
        error = ErrorResponse(**data)
        
        assert error.error == "ValidationError"
        assert error.message == "Invalid input"
        assert error.detail["field"] == "symbol"

    def test_error_response_without_detail(self):
        """Test creating ErrorResponse without detail."""
        data = {
            "error": "NotFound",
            "message": "Resource not found",
        }
        
        error = ErrorResponse(**data)
        
        assert error.error == "NotFound"
        assert error.message == "Resource not found"
        assert error.detail is None

    def test_error_response_default_timestamp(self):
        """Test that timestamp is auto-generated."""
        error = ErrorResponse(
            error="TestError",
            message="Test message",
        )
        
        assert isinstance(error.timestamp, datetime)

    def test_error_response_serialization(self):
        """Test serializing ErrorResponse to dict."""
        error = ErrorResponse(
            error="RateLimitExceeded",
            message="Too many requests",
            detail={"retry_after": 60},
        )
        
        data = error.model_dump()
        
        assert data["error"] == "RateLimitExceeded"
        assert data["detail"]["retry_after"] == 60
        assert "timestamp" in data

    def test_error_response_required_fields(self):
        """Test that required fields are validated."""
        with pytest.raises(ValidationError):
            ErrorResponse()  # Missing required fields

    def test_error_response_with_complex_detail(self):
        """Test ErrorResponse with complex nested detail."""
        detail = {
            "errors": [
                {"field": "symbol", "message": "required"},
                {"field": "interval", "message": "invalid"},
            ],
            "request_id": "12345",
        }
        
        error = ErrorResponse(
            error="ValidationError",
            message="Multiple validation errors",
            detail=detail,
        )
        
        assert len(error.detail["errors"]) == 2
        assert error.detail["request_id"] == "12345"


@pytest.mark.unit
class TestSuccessResponseModel:
    """Tests for SuccessResponse model."""

    def test_success_response_valid_data(self):
        """Test creating SuccessResponse with valid data."""
        data = {
            "success": True,
            "message": "Operation completed",
            "data": {"id": 123, "name": "Test"},
        }
        
        response = SuccessResponse(**data)
        
        assert response.success is True
        assert response.message == "Operation completed"
        assert response.data["id"] == 123

    def test_success_response_default_success(self):
        """Test that success defaults to True."""
        response = SuccessResponse(message="Done")
        
        assert response.success is True

    def test_success_response_without_data(self):
        """Test creating SuccessResponse without data."""
        response = SuccessResponse(
            message="Operation completed",
        )
        
        assert response.success is True
        assert response.message == "Operation completed"
        assert response.data is None

    def test_success_response_default_timestamp(self):
        """Test that timestamp is auto-generated."""
        response = SuccessResponse(message="Test")
        
        assert isinstance(response.timestamp, datetime)

    def test_success_response_serialization(self):
        """Test serializing SuccessResponse to dict."""
        response = SuccessResponse(
            message="Created",
            data={"id": 1},
        )
        
        data = response.model_dump()
        
        assert data["success"] is True
        assert data["message"] == "Created"
        assert data["data"]["id"] == 1
        assert "timestamp" in data

    def test_success_response_with_list_data(self):
        """Test SuccessResponse with list as data."""
        items = [
            {"id": 1, "name": "Item 1"},
            {"id": 2, "name": "Item 2"},
        ]
        
        response = SuccessResponse(
            message="Items retrieved",
            data=items,
        )
        
        assert len(response.data) == 2
        assert response.data[0]["name"] == "Item 1"

    def test_success_response_with_complex_data(self):
        """Test SuccessResponse with complex nested data."""
        complex_data = {
            "quotes": [
                {"symbol": "AAPL", "price": 150.25},
                {"symbol": "GOOGL", "price": 2800.00},
            ],
            "metadata": {
                "total": 2,
                "timestamp": "2026-03-06T14:00:00Z",
            },
        }
        
        response = SuccessResponse(
            message="Quotes fetched",
            data=complex_data,
        )
        
        assert len(response.data["quotes"]) == 2
        assert response.data["metadata"]["total"] == 2
