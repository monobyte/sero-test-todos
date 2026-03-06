"""
Health check and system status endpoints.
"""
from datetime import datetime

from fastapi import APIRouter, status

from config import settings
from models import HealthCheck
from utils import cache_manager, rate_limiter, get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/health", tags=["Health"])


@router.get(
    "",
    response_model=HealthCheck,
    status_code=status.HTTP_200_OK,
    summary="Health check",
    description="Check the health status of the API and its dependencies",
)
async def health_check() -> HealthCheck:
    """
    Comprehensive health check endpoint.
    
    Returns:
        HealthCheck model with service status
    """
    # Check which API keys are configured
    services_status = {
        "finnhub": bool(settings.finnhub_api_key),
        "fmp": bool(settings.fmp_api_key),
        "alpha_vantage": bool(settings.alpha_vantage_api_key),
        "twelve_data": bool(settings.twelve_data_api_key),
        "coingecko": bool(settings.coingecko_api_key),
    }

    logger.info("health_check_requested", services=services_status)

    return HealthCheck(
        status="healthy",
        timestamp=datetime.utcnow(),
        version="0.1.0",
        environment=settings.app_env,
        services=services_status,
    )


@router.get(
    "/cache",
    summary="Cache statistics",
    description="Get current cache statistics and sizes",
)
async def cache_stats() -> dict:
    """
    Get cache statistics.
    
    Returns:
        Cache stats including sizes and TTLs
    """
    stats = cache_manager.get_stats()
    logger.info("cache_stats_requested", stats=stats)
    return stats


@router.get(
    "/rate-limits",
    summary="Rate limit status",
    description="Get current rate limiting status for all services",
)
async def rate_limit_stats() -> dict:
    """
    Get rate limiter statistics.
    
    Returns:
        Rate limit stats per service
    """
    stats = rate_limiter.get_stats()
    logger.info("rate_limit_stats_requested", stats=stats)
    return stats
