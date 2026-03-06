"""
API route handlers.
Each router module defines endpoints for specific functionality.
"""
from .health import router as health_router

__all__ = ["health_router"]
