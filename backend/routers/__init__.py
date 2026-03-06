"""
API route handlers.
Each router module defines endpoints for specific functionality.
"""
from .health import router as health_router
from .historical import router as historical_router
from .quotes import router as quotes_router
from .screener import router as screener_router
from .websocket import router as websocket_router

__all__ = [
    "health_router",
    "historical_router",
    "quotes_router",
    "screener_router",
    "websocket_router",
]
