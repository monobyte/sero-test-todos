"""
Market Monitor Backend - FastAPI Application

A personal finance/trading research application backend providing:
- Real-time stock and crypto price monitoring
- Historical market data with OHLCV candles
- Trading idea generation and screening
- WebSocket support for live price feeds

Built with FastAPI, integrating multiple free-tier financial data APIs:
- Finnhub (stocks, WebSocket quotes)
- CoinGecko (crypto)
- yfinance (historical data fallback)
- Financial Modeling Prep (fundamentals)
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from config import settings
from models import ErrorResponse
from routers import health_router
from utils import setup_logging, get_logger

# Setup structured logging
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Application lifespan manager.
    
    Handles startup and shutdown tasks:
    - Log application start
    - Initialize services
    - Cleanup on shutdown
    """
    # Startup
    logger.info(
        "application_starting",
        environment=settings.app_env,
        host=settings.app_host,
        port=settings.app_port,
    )
    
    # Check API key configuration
    if not settings.finnhub_api_key:
        logger.warning("finnhub_api_key_missing", message="Finnhub features will be limited")
    if not settings.coingecko_api_key:
        logger.warning("coingecko_api_key_missing", message="CoinGecko features will be limited")
    
    yield
    
    # Shutdown
    logger.info("application_shutting_down")


# Initialize FastAPI application
app = FastAPI(
    title="Market Monitor API",
    description=(
        "Personal finance and trading research application. "
        "Monitor stocks and crypto, analyze historical data, generate trading ideas."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

logger.info(
    "cors_configured",
    allowed_origins=settings.cors_origins_list,
)


# Global exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Handle Pydantic validation errors with structured responses.
    
    Args:
        request: FastAPI request object
        exc: Validation error exception
        
    Returns:
        JSON error response
    """
    logger.warning(
        "validation_error",
        path=request.url.path,
        errors=exc.errors(),
    )
    
    error_response = ErrorResponse(
        error="ValidationError",
        message="Request validation failed",
        detail={"errors": exc.errors()},
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response.model_dump(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle unexpected exceptions with structured responses.
    
    Args:
        request: FastAPI request object
        exc: Exception
        
    Returns:
        JSON error response
    """
    logger.error(
        "unexpected_error",
        path=request.url.path,
        error=str(exc),
        exc_info=True,
    )
    
    error_response = ErrorResponse(
        error="InternalServerError",
        message="An unexpected error occurred" if settings.is_production else str(exc),
        detail={"path": request.url.path} if settings.is_production else {"error": str(exc)},
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.model_dump(),
    )


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Log all HTTP requests with timing information.
    
    Args:
        request: FastAPI request
        call_next: Next middleware in chain
        
    Returns:
        Response from next middleware
    """
    import time
    
    start_time = time.time()
    
    logger.info(
        "request_started",
        method=request.method,
        path=request.url.path,
        client=request.client.host if request.client else None,
    )
    
    response = await call_next(request)
    
    duration = time.time() - start_time
    
    logger.info(
        "request_completed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round(duration * 1000, 2),
    )
    
    return response


# Include routers
app.include_router(health_router)

# Future routers will be added here:
# app.include_router(quotes_router)
# app.include_router(historical_router)
# app.include_router(screener_router)
# app.include_router(websocket_router)


@app.get("/", summary="Root endpoint", tags=["Root"])
async def root():
    """
    Root endpoint with API information.
    
    Returns:
        Welcome message and links
    """
    return {
        "message": "Market Monitor API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn
    
    # Run with uvicorn when executed directly
    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
    )
