"""
Market data models for quotes, historical data, and market status.
"""
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class AssetType(str, Enum):
    """Asset type enumeration."""

    STOCK = "stock"
    CRYPTO = "crypto"
    ETF = "etf"
    INDEX = "index"


class MarketStatus(str, Enum):
    """Market status enumeration."""

    OPEN = "open"
    CLOSED = "closed"
    PRE_MARKET = "pre_market"
    AFTER_HOURS = "after_hours"


class Quote(BaseModel):
    """Real-time or delayed quote data."""

    symbol: str = Field(..., description="Ticker symbol or crypto pair")
    asset_type: AssetType = Field(..., description="Type of asset")
    price: float = Field(..., description="Current price")
    change: float = Field(..., description="Price change")
    change_percent: float = Field(..., description="Percentage change")
    volume: Optional[float] = Field(None, description="Trading volume")
    market_cap: Optional[float] = Field(None, description="Market capitalization")
    high_24h: Optional[float] = Field(None, description="24-hour high")
    low_24h: Optional[float] = Field(None, description="24-hour low")
    open_price: Optional[float] = Field(None, description="Opening price")
    previous_close: Optional[float] = Field(None, description="Previous close price")
    timestamp: datetime = Field(..., description="Quote timestamp")
    source: str = Field(..., description="Data source (finnhub, coingecko, etc.)")

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "AAPL",
                "asset_type": "stock",
                "price": 178.50,
                "change": 2.35,
                "change_percent": 1.33,
                "volume": 52347890,
                "market_cap": 2800000000000,
                "high_24h": 179.20,
                "low_24h": 176.80,
                "open_price": 177.00,
                "previous_close": 176.15,
                "timestamp": "2026-03-06T14:00:00Z",
                "source": "finnhub",
            }
        }


class OHLCV(BaseModel):
    """OHLCV candle data point."""

    timestamp: datetime = Field(..., description="Candle timestamp")
    open: float = Field(..., description="Opening price")
    high: float = Field(..., description="Highest price")
    low: float = Field(..., description="Lowest price")
    close: float = Field(..., description="Closing price")
    volume: float = Field(..., description="Trading volume")

    class Config:
        json_schema_extra = {
            "example": {
                "timestamp": "2026-03-06T00:00:00Z",
                "open": 177.00,
                "high": 179.20,
                "low": 176.80,
                "close": 178.50,
                "volume": 52347890,
            }
        }


class HistoricalData(BaseModel):
    """Historical price data with OHLCV candles."""

    symbol: str = Field(..., description="Ticker symbol or crypto pair")
    asset_type: AssetType = Field(..., description="Type of asset")
    interval: str = Field(..., description="Data interval (1d, 1h, 5m, etc.)")
    candles: List[OHLCV] = Field(..., description="List of OHLCV candles")
    source: str = Field(..., description="Data source")

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "AAPL",
                "asset_type": "stock",
                "interval": "1d",
                "candles": [
                    {
                        "timestamp": "2026-03-06T00:00:00Z",
                        "open": 177.00,
                        "high": 179.20,
                        "low": 176.80,
                        "close": 178.50,
                        "volume": 52347890,
                    }
                ],
                "source": "yfinance",
            }
        }


class CompanyProfile(BaseModel):
    """Company profile and fundamental data from Finnhub."""

    symbol: str = Field(..., description="Ticker symbol")
    name: str = Field(..., description="Company name")
    exchange: Optional[str] = Field(None, description="Stock exchange (NASDAQ, NYSE, etc.)")
    country: Optional[str] = Field(None, description="Country of incorporation")
    currency: Optional[str] = Field(None, description="Trading currency")
    industry: Optional[str] = Field(None, description="Industry classification")
    ipo_date: Optional[str] = Field(None, description="IPO date (YYYY-MM-DD)")
    market_cap: Optional[float] = Field(None, description="Market capitalisation in millions USD")
    shares_outstanding: Optional[float] = Field(None, description="Shares outstanding in millions")
    website: Optional[str] = Field(None, description="Company website URL")
    logo: Optional[str] = Field(None, description="Company logo URL")
    phone: Optional[str] = Field(None, description="Company phone number")
    source: str = Field(..., description="Data source")

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "AAPL",
                "name": "Apple Inc",
                "exchange": "NASDAQ/NMS (Global Select Market)",
                "country": "US",
                "currency": "USD",
                "industry": "Technology",
                "ipo_date": "1980-12-12",
                "market_cap": 2800000.0,
                "shares_outstanding": 15441.88,
                "website": "https://www.apple.com/",
                "logo": "https://static.finnhub.io/logo/87cb30d8.png",
                "phone": "14089961010",
                "source": "finnhub",
            }
        }
