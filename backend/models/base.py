"""
Base models for API responses and common data structures.
"""
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class HealthCheck(BaseModel):
    """Health check response model."""

    status: str = Field(..., description="Service status")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Current timestamp")
    version: str = Field(default="0.1.0", description="API version")
    environment: str = Field(..., description="Environment (development/production)")
    services: Dict[str, bool] = Field(
        default_factory=dict, description="Status of external services"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "timestamp": "2026-03-06T14:00:00Z",
                "version": "0.1.0",
                "environment": "development",
                "services": {
                    "finnhub": True,
                    "coingecko": True,
                    "yfinance": True,
                },
            }
        }


class ErrorResponse(BaseModel):
    """Standard error response model."""

    error: str = Field(..., description="Error type or code")
    message: str = Field(..., description="Human-readable error message")
    detail: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "RateLimitExceeded",
                "message": "API rate limit exceeded. Please try again later.",
                "detail": {"retry_after": 60},
                "timestamp": "2026-03-06T14:00:00Z",
            }
        }


class SuccessResponse(BaseModel):
    """Standard success response model."""

    success: bool = Field(default=True, description="Operation success status")
    message: str = Field(..., description="Success message")
    data: Optional[Any] = Field(None, description="Response data")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Operation completed successfully",
                "data": {},
                "timestamp": "2026-03-06T14:00:00Z",
            }
        }
