"""
Service layer for external API integrations.
Each service module handles a specific data provider with fallback logic.
"""
from .base import (
    AuthenticationError,
    BaseService,
    CacheType,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ServiceError,
)
from .fmp_service import FMPService
from .yfinance_service import YFinanceService

from .coingecko_service import CoinGeckoService, SYMBOL_TO_COINGECKO_ID

# Future services (not yet implemented in this subtask)
# from .finnhub_service import FinnhubService

__all__ = [
    # Base
    "BaseService",
    "ServiceError",
    "RateLimitError",
    "AuthenticationError",
    "NotFoundError",
    "NetworkError",
    "CacheType",
    # Concrete services
    "CoinGeckoService",
    "SYMBOL_TO_COINGECKO_ID",
    "YFinanceService",
    "FMPService",
]
