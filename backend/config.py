"""
Application configuration using Pydantic Settings.
Loads environment variables from .env file.
"""
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application Settings
    app_env: str = Field(default="development", description="Application environment")
    app_host: str = Field(default="0.0.0.0", description="Host to bind the server")
    app_port: int = Field(default=8000, description="Port to bind the server")
    log_level: str = Field(default="INFO", description="Logging level")

    # CORS Settings
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:5185,http://192.168.64.15:3000",
        description="Comma-separated list of allowed origins",
    )

    # Stock Data APIs
    finnhub_api_key: str = Field(default="", description="Finnhub API key")
    fmp_api_key: str = Field(default="", description="Financial Modeling Prep API key")
    alpha_vantage_api_key: str = Field(default="", description="Alpha Vantage API key")
    twelve_data_api_key: str = Field(default="", description="Twelve Data API key")

    # Crypto Data APIs
    coingecko_api_key: str = Field(default="", description="CoinGecko API key")

    # Cache Settings
    cache_ttl_quotes: int = Field(default=60, description="Cache TTL for quotes in seconds")
    cache_ttl_historical: int = Field(
        default=3600, description="Cache TTL for historical data in seconds"
    )
    cache_ttl_fundamentals: int = Field(
        default=86400, description="Cache TTL for fundamentals in seconds"
    )

    # Rate Limiting
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_calls_per_minute: int = Field(
        default=50, description="Max API calls per minute"
    )

    # WebSocket Settings
    ws_ping_interval: int = Field(default=30, description="WebSocket ping interval in seconds")
    ws_ping_timeout: int = Field(default=10, description="WebSocket ping timeout in seconds")
    ws_max_connections: int = Field(default=100, description="Max WebSocket connections")

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.app_env.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.app_env.lower() == "development"


# Global settings instance
settings = Settings()
