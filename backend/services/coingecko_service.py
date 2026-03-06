"""
CoinGecko service for cryptocurrency market data.

CoinGecko is the primary cryptocurrency data provider, offering:
- Real-time crypto prices via /simple/price and /coins/markets
- Historical OHLCV data via /coins/{id}/market_chart
- Trending coins via /search/trending
- Market rankings and capitalization data

Free Tier (Demo API key):
- ~30 calls/minute
- 10,000 calls/month (caching dramatically reduces usage)

Pro Tier (Pro API key):
- Higher rate limits
- Access to additional endpoints

API Documentation: https://www.coingecko.com/api/documentation

Authentication:
- Demo API key: sent as `x-cg-demo-api-key` header
- Pro API key: sent as `x-cg-pro-api-key` header
- Both can alternatively be sent as query params

Symbol Resolution:
- CoinGecko uses IDs (e.g., "bitcoin") not ticker symbols (e.g., "BTC")
- Common symbols are resolved via SYMBOL_TO_COINGECKO_ID lookup table
- Unknown symbols fall back to the /search endpoint
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import settings
from models.market import AssetType, HistoricalData, OHLCV, Quote
from utils.logger import get_logger
from .base import BaseService, CacheType, NotFoundError, ServiceError

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Symbol → CoinGecko ID lookup table
# Covers the most commonly traded cryptocurrencies.
# Symbols are intentionally uppercase; lookups normalise to upper.
# ---------------------------------------------------------------------------
SYMBOL_TO_COINGECKO_ID: Dict[str, str] = {
    # --- Major Layer-1s ---
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "ADA": "cardano",
    "AVAX": "avalanche-2",
    "DOT": "polkadot",
    "ATOM": "cosmos",
    "NEAR": "near",
    "APT": "aptos",
    "SUI": "sui",
    "TON": "the-open-network",
    "TRX": "tron",
    "ETC": "ethereum-classic",
    "FTM": "fantom",
    "ALGO": "algorand",
    "EGLD": "elrond-erd-2",
    "KLAY": "klay-token",
    "CELO": "celo",
    "FLOW": "flow",
    "ROSE": "oasis-network",
    "XTZ": "tezos",
    "LUNA": "terra-luna-2",
    "LUNC": "terra-luna",
    "DCR": "decred",
    # --- Major Altcoins ---
    "BNB": "binancecoin",
    "XRP": "ripple",
    "DOGE": "dogecoin",
    "SHIB": "shiba-inu",
    "LTC": "litecoin",
    "BCH": "bitcoin-cash",
    "XLM": "stellar",
    "XMR": "monero",
    "ZEC": "zcash",
    "DASH": "dash",
    "WAVES": "waves",
    "KSM": "kusama",
    "VET": "vechain",
    "ZIL": "zilliqa",
    "XEM": "nem",
    "DGB": "digibyte",
    "RVN": "ravencoin",
    # --- Layer-2 / Scaling ---
    "MATIC": "matic-network",
    "POL": "matic-network",
    "ARB": "arbitrum",
    "OP": "optimism",
    "IMX": "immutable-x",
    "RUNE": "thorchain",
    "SEI": "sei-network",
    # --- DeFi ---
    "UNI": "uniswap",
    "LINK": "chainlink",
    "AAVE": "aave",
    "MKR": "maker",
    "CRV": "curve-dao-token",
    "SNX": "havven",
    "COMP": "compound-governance-token",
    "1INCH": "1inch",
    "SUSHI": "sushi",
    "YFI": "yearn-finance",
    "CAKE": "pancakeswap-token",
    "GRT": "the-graph",
    "BNT": "bancor",
    "KNC": "kyber-network-crystal",
    "ZRX": "0x",
    "REN": "republic-protocol",
    "LDO": "lido-dao",
    "RPL": "rocket-pool",
    "BAL": "balancer",
    "FXS": "frax-share",
    # --- Stablecoins ---
    "USDT": "tether",
    "USDC": "usd-coin",
    "DAI": "dai",
    "BUSD": "binance-usd",
    "TUSD": "true-usd",
    "FRAX": "frax",
    "GUSD": "gemini-dollar",
    "USDP": "paxos-standard",
    # --- Wrapped / LSTs ---
    "WBTC": "wrapped-bitcoin",
    "STETH": "staked-ether",
    "RETH": "rocket-pool-eth",
    "CBETH": "coinbase-wrapped-staked-eth",
    # --- Gaming / NFT ---
    "SAND": "the-sandbox",
    "MANA": "decentraland",
    "AXS": "axie-infinity",
    "ENJ": "enjincoin",
    "CHZ": "chiliz",
    "ILV": "illuvium",
    "GALA": "gala",
    # --- Infrastructure ---
    "FIL": "filecoin",
    "ICP": "internet-computer",
    "THETA": "theta-token",
    "OCEAN": "ocean-protocol",
    "BAT": "basic-attention-token",
    "HBAR": "hedera-hashgraph",
    "SCRT": "secret",
    "EOS": "eos",
    # --- Exchange tokens ---
    "CRO": "crypto-com-chain",
    # --- Meme coins ---
    "PEPE": "pepe",
    "FLOKI": "floki",
    "BONK": "bonk",
    "WIF": "dogwifcoin",
    # --- Other notable ---
    "PAXG": "pax-gold",
    "INJ": "injective-protocol",
    "TIA": "celestia",
    "PYTH": "pyth-network",
    "JTO": "jito-governance-token",
}

# Default vs_currency for all price calculations
_DEFAULT_VS_CURRENCY = "usd"


class CoinGeckoService(BaseService):
    """
    CoinGecko API integration for cryptocurrency market data.

    Provides real-time and historical crypto data sourced from CoinGecko's
    public and Pro APIs. All requests are automatically cached and rate-limited
    using the shared infrastructure from BaseService.

    Usage::

        async with CoinGeckoService() as cg:
            quote = await cg.get_crypto_quote("BTC")
            trending = await cg.get_trending()
            top = await cg.get_top_coins(limit=50)

    Without API key the public endpoint is used; with a key (demo or pro)
    the appropriate authenticated URL is selected automatically.
    """

    SERVICE_NAME = "coingecko"

    # Public (no-key) base URL
    _BASE_URL_PUBLIC = "https://api.coingecko.com/api/v3"

    # Demo key base URL (same host, but key unlocks higher limits)
    _BASE_URL_DEMO = "https://api.coingecko.com/api/v3"

    # Pro key base URL
    _BASE_URL_PRO = "https://pro-api.coingecko.com/api/v3"

    # CoinGecko free tier: ~30 calls/min; we stay conservative
    MAX_RETRIES: int = 3
    RETRY_BACKOFF_FACTOR: float = 2.0

    def _get_base_url(self) -> str:
        """
        Select API base URL based on configured API key.

        - Pro key  → pro-api.coingecko.com
        - Demo key → api.coingecko.com  (with x-cg-demo-api-key header)
        - No key   → api.coingecko.com  (public, lower limits)
        """
        api_key = settings.coingecko_api_key
        if api_key and api_key.startswith("CG-"):
            # Pro keys start with "CG-"
            return self._BASE_URL_PRO
        return self._BASE_URL_DEMO

    def _get_api_key(self) -> str:
        """Return CoinGecko API key from settings."""
        return settings.coingecko_api_key

    def _get_default_headers(self) -> Dict[str, str]:
        """
        Build request headers, injecting the appropriate API key header.

        CoinGecko uses different header names for demo vs pro keys:
        - Demo: ``x-cg-demo-api-key``
        - Pro:  ``x-cg-pro-api-key``
        """
        headers = super()._get_default_headers()
        api_key = self._get_api_key()
        if api_key:
            if api_key.startswith("CG-"):
                headers["x-cg-pro-api-key"] = api_key
            else:
                headers["x-cg-demo-api-key"] = api_key
        return headers

    # ------------------------------------------------------------------
    # Symbol / ID resolution
    # ------------------------------------------------------------------

    def _symbol_to_id(self, symbol: str) -> Optional[str]:
        """
        Resolve a ticker symbol to a CoinGecko coin ID using the static table.

        Args:
            symbol: Cryptocurrency ticker (case-insensitive, e.g. "BTC").

        Returns:
            CoinGecko coin ID or ``None`` if not in the lookup table.
        """
        return SYMBOL_TO_COINGECKO_ID.get(symbol.upper())

    async def resolve_coin_id(self, symbol: str) -> str:
        """
        Resolve a ticker symbol or CoinGecko ID to a canonical CoinGecko ID.

        Resolution order:
        1. Static lookup table (no API call, no rate limit consumed)
        2. CoinGecko ``/search`` endpoint (fallback for unlisted symbols)

        Args:
            symbol: Ticker symbol (e.g. "BTC") or CoinGecko ID (e.g. "bitcoin").

        Returns:
            CoinGecko coin ID string.

        Raises:
            NotFoundError: If the symbol cannot be resolved.
        """
        # --- Static table ---
        coin_id = self._symbol_to_id(symbol)
        if coin_id:
            return coin_id

        # Already looks like a CoinGecko ID (lowercase, hyphenated)?
        if symbol == symbol.lower() and symbol.replace("-", "").isalpha():
            return symbol

        # --- API search fallback ---
        self._logger.info(
            "symbol_lookup_fallback",
            service=self.SERVICE_NAME,
            symbol=symbol,
        )
        try:
            results = await self._make_request(
                method="GET",
                endpoint="/search",
                params={"query": symbol},
                cache_type=CacheType.FUNDAMENTAL,
                cache_key_parts=["search", symbol.lower()],
            )
            coins: List[Dict[str, Any]] = results.get("coins", [])

            # Prefer exact symbol match first, then partial match
            symbol_upper = symbol.upper()
            for coin in coins:
                if coin.get("symbol", "").upper() == symbol_upper:
                    return coin["id"]

            # No exact match — take first result if any
            if coins:
                return coins[0]["id"]

        except ServiceError as exc:
            self._logger.warning(
                "symbol_search_failed",
                service=self.SERVICE_NAME,
                symbol=symbol,
                error=str(exc),
            )

        raise NotFoundError(
            service=self.SERVICE_NAME,
            resource=symbol,
            message=f"Cryptocurrency '{symbol}' not found on CoinGecko",
        )

    # ------------------------------------------------------------------
    # Quote
    # ------------------------------------------------------------------

    async def get_crypto_quote(self, symbol: str) -> Quote:
        """
        Fetch a real-time cryptocurrency quote.

        Uses ``/coins/markets`` to retrieve a single coin's full market data,
        including price, 24 h change, volume, market cap, and high/low.

        Args:
            symbol: Ticker symbol (e.g. "BTC", "ETH") or CoinGecko ID
                    (e.g. "bitcoin").

        Returns:
            Populated :class:`~models.market.Quote` object.

        Raises:
            NotFoundError: If the cryptocurrency is not found.
            RateLimitError: If the CoinGecko rate limit is exceeded.
            ServiceError: For other API errors.

        Example::

            async with CoinGeckoService() as cg:
                quote = await cg.get_crypto_quote("BTC")
                print(f"{quote.symbol}: ${quote.price:,.2f}")
        """
        coin_id = await self.resolve_coin_id(symbol)

        data = await self._make_request(
            method="GET",
            endpoint="/coins/markets",
            params={
                "vs_currency": _DEFAULT_VS_CURRENCY,
                "ids": coin_id,
                "order": "market_cap_desc",
                "per_page": 1,
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "24h",
            },
            cache_type=CacheType.QUOTE,
            cache_key_parts=["quote", coin_id],
        )

        if not data or not isinstance(data, list) or len(data) == 0:
            raise NotFoundError(
                service=self.SERVICE_NAME,
                resource=symbol,
                message=f"No market data returned for '{symbol}'",
            )

        return self._parse_market_item_to_quote(symbol.upper(), data[0])

    async def get_crypto_quotes_batch(
        self, symbols: List[str]
    ) -> Dict[str, Quote]:
        """
        Fetch quotes for multiple cryptocurrencies in a single API call.

        Resolves all symbols concurrently (via the static table) and batches
        them into one ``/coins/markets`` request.

        Args:
            symbols: List of ticker symbols (e.g. ["BTC", "ETH", "SOL"]).

        Returns:
            Dict mapping each requested symbol (upper-case) to its Quote.
            Symbols that could not be resolved are omitted from the result.

        Example::

            async with CoinGeckoService() as cg:
                quotes = await cg.get_crypto_quotes_batch(["BTC", "ETH"])
        """
        # Resolve symbols → CoinGecko IDs (best-effort; skip unknown)
        id_to_symbol: Dict[str, str] = {}
        for sym in symbols:
            coin_id = self._symbol_to_id(sym)
            if coin_id:
                id_to_symbol[coin_id] = sym.upper()
            else:
                self._logger.warning(
                    "symbol_not_in_lookup_table",
                    service=self.SERVICE_NAME,
                    symbol=sym,
                )

        if not id_to_symbol:
            return {}

        ids_param = ",".join(id_to_symbol.keys())
        cache_key = "batch:" + ":".join(sorted(id_to_symbol.keys()))

        data = await self._make_request(
            method="GET",
            endpoint="/coins/markets",
            params={
                "vs_currency": _DEFAULT_VS_CURRENCY,
                "ids": ids_param,
                "order": "market_cap_desc",
                "per_page": 250,
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "24h",
            },
            cache_type=CacheType.QUOTE,
            cache_key_parts=["batch_quote", cache_key],
        )

        result: Dict[str, Quote] = {}
        for item in data or []:
            coin_id = item.get("id", "")
            original_symbol = id_to_symbol.get(coin_id, coin_id.upper())
            try:
                result[original_symbol] = self._parse_market_item_to_quote(
                    original_symbol, item
                )
            except (KeyError, TypeError, ValueError) as exc:
                self._logger.warning(
                    "quote_parse_error",
                    service=self.SERVICE_NAME,
                    coin_id=coin_id,
                    error=str(exc),
                )

        return result

    # ------------------------------------------------------------------
    # Trending coins
    # ------------------------------------------------------------------

    async def get_trending(self) -> List[Dict[str, Any]]:
        """
        Retrieve the currently trending cryptocurrencies on CoinGecko.

        CoinGecko's ``/search/trending`` returns the top-7 coins searched
        in the last 24 hours, along with NFTs and DeFi categories.

        Returns:
            List of trending coin dictionaries, each containing:

            - ``id`` (str): CoinGecko coin ID
            - ``name`` (str): Full name (e.g. "Bitcoin")
            - ``symbol`` (str): Ticker symbol (upper-case)
            - ``market_cap_rank`` (int | None): Global market cap rank
            - ``price_usd`` (float | None): Current USD price
            - ``price_change_24h_pct`` (float | None): 24h % change
            - ``thumb`` (str | None): Small thumbnail URL
            - ``large`` (str | None): Large image URL
            - ``score`` (int): Trending score (0 = #1 trending)

        Raises:
            ServiceError: If the trending endpoint fails.

        Example::

            async with CoinGeckoService() as cg:
                coins = await cg.get_trending()
                for coin in coins:
                    print(coin["name"], coin["symbol"])
        """
        data = await self._make_request(
            method="GET",
            endpoint="/search/trending",
            cache_type=CacheType.QUOTE,
            cache_key_parts=["trending"],
        )

        raw_coins: List[Dict[str, Any]] = data.get("coins", [])
        trending: List[Dict[str, Any]] = []

        for entry in raw_coins:
            item = entry.get("item", {})
            if not item:
                continue

            # CoinGecko v3 nests price data in item.data for some keys
            item_data = item.get("data", {})
            price_usd: Optional[float] = None
            price_change_24h: Optional[float] = None

            # Try item.data first (newer API format), then item directly
            if item_data:
                try:
                    price_usd = float(item_data.get("price", 0) or 0) or None
                except (TypeError, ValueError):
                    pass
                try:
                    price_change_24h = float(
                        item_data.get("price_change_percentage_24h", {}).get(
                            "usd", 0
                        ) or 0
                    )
                except (TypeError, ValueError, AttributeError):
                    pass

            trending.append(
                {
                    "id": item.get("id", ""),
                    "name": item.get("name", ""),
                    "symbol": item.get("symbol", "").upper(),
                    "market_cap_rank": item.get("market_cap_rank"),
                    "price_usd": price_usd,
                    "price_change_24h_pct": price_change_24h,
                    "thumb": item.get("thumb"),
                    "large": item.get("large"),
                    "score": item.get("score", 0),
                }
            )

        self._logger.info(
            "trending_fetched",
            service=self.SERVICE_NAME,
            count=len(trending),
        )
        return trending

    # ------------------------------------------------------------------
    # Market cap / market data
    # ------------------------------------------------------------------

    async def get_top_coins(
        self,
        limit: int = 100,
        vs_currency: str = _DEFAULT_VS_CURRENCY,
    ) -> List[Dict[str, Any]]:
        """
        Fetch the top cryptocurrencies ranked by market capitalisation.

        Args:
            limit: Number of coins to return (1–250, default 100).
            vs_currency: Target currency for prices (default "usd").

        Returns:
            List of market data dictionaries (see :meth:`get_coin_market_data`
            for the shape of each entry), ordered by market cap descending.

        Raises:
            ServiceError: If the API request fails.

        Example::

            async with CoinGeckoService() as cg:
                top50 = await cg.get_top_coins(limit=50)
                for coin in top50:
                    print(f"#{coin['market_cap_rank']} {coin['symbol']}: "
                          f"${coin['market_cap']:,.0f}")
        """
        limit = max(1, min(250, limit))

        data = await self._make_request(
            method="GET",
            endpoint="/coins/markets",
            params={
                "vs_currency": vs_currency,
                "order": "market_cap_desc",
                "per_page": limit,
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "24h",
            },
            cache_type=CacheType.FUNDAMENTAL,
            cache_key_parts=["top_coins", vs_currency, str(limit)],
        )

        return [self._parse_market_item_to_dict(item) for item in (data or [])]

    async def get_coin_market_data(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch detailed market data for a single cryptocurrency.

        Returns a rich dictionary suitable for dashboard display, including
        market cap, circulating supply, ATH, and price change over multiple
        time horizons.

        Args:
            symbol: Ticker symbol (e.g. "BTC") or CoinGecko ID ("bitcoin").

        Returns:
            Dictionary containing:

            - ``id`` (str): CoinGecko coin ID
            - ``symbol`` (str): Ticker symbol (upper-case)
            - ``name`` (str): Full name
            - ``current_price`` (float): Current price in USD
            - ``market_cap`` (float): Market capitalisation in USD
            - ``market_cap_rank`` (int): Global rank by market cap
            - ``fully_diluted_valuation`` (float | None): FDV in USD
            - ``total_volume`` (float): 24h trading volume in USD
            - ``high_24h`` (float): 24h high price
            - ``low_24h`` (float): 24h low price
            - ``price_change_24h`` (float): Absolute price change over 24h
            - ``price_change_percentage_24h`` (float): % price change over 24h
            - ``market_cap_change_24h`` (float): Market cap change over 24h
            - ``market_cap_change_percentage_24h`` (float): Market cap % change
            - ``circulating_supply`` (float | None): Circulating supply
            - ``total_supply`` (float | None): Total supply
            - ``max_supply`` (float | None): Maximum supply
            - ``ath`` (float): All-time high price
            - ``ath_change_percentage`` (float): % change from ATH
            - ``ath_date`` (str): ISO date of ATH
            - ``last_updated`` (str): ISO timestamp of last update

        Raises:
            NotFoundError: If the coin is not found.
            ServiceError: For other API errors.
        """
        coin_id = await self.resolve_coin_id(symbol)

        data = await self._make_request(
            method="GET",
            endpoint="/coins/markets",
            params={
                "vs_currency": _DEFAULT_VS_CURRENCY,
                "ids": coin_id,
                "order": "market_cap_desc",
                "per_page": 1,
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "24h,7d,30d",
            },
            cache_type=CacheType.FUNDAMENTAL,
            cache_key_parts=["market_data", coin_id],
        )

        if not data or not isinstance(data, list) or len(data) == 0:
            raise NotFoundError(
                service=self.SERVICE_NAME,
                resource=symbol,
                message=f"No market data found for '{symbol}'",
            )

        return self._parse_market_item_to_dict(data[0])

    async def get_global_market_data(self) -> Dict[str, Any]:
        """
        Fetch global cryptocurrency market statistics.

        Returns:
            Dictionary containing global crypto market metrics such as total
            market cap, 24h volume, BTC dominance, and active coin count.

        Raises:
            ServiceError: If the API request fails.
        """
        data = await self._make_request(
            method="GET",
            endpoint="/global",
            cache_type=CacheType.FUNDAMENTAL,
            cache_key_parts=["global"],
        )

        raw = data.get("data", {}) if isinstance(data, dict) else {}

        total_market_cap = raw.get("total_market_cap", {})
        total_volume = raw.get("total_volume", {})
        market_cap_pct = raw.get("market_cap_percentage", {})

        return {
            "total_market_cap_usd": total_market_cap.get("usd"),
            "total_24h_volume_usd": total_volume.get("usd"),
            "market_cap_change_percentage_24h_usd": raw.get(
                "market_cap_change_percentage_24h_usd"
            ),
            "btc_dominance": market_cap_pct.get("btc"),
            "eth_dominance": market_cap_pct.get("eth"),
            "active_cryptocurrencies": raw.get("active_cryptocurrencies"),
            "markets": raw.get("markets"),
            "last_updated": raw.get("updated_at"),
        }

    # ------------------------------------------------------------------
    # Historical data
    # ------------------------------------------------------------------

    async def get_historical(
        self,
        symbol: str,
        days: int = 30,
        vs_currency: str = _DEFAULT_VS_CURRENCY,
        interval: Optional[str] = None,
    ) -> HistoricalData:
        """
        Fetch historical OHLCV data for a cryptocurrency.

        CoinGecko's ``/coins/{id}/market_chart`` returns price, market cap,
        and volume arrays at automatically chosen granularity:

        - 1 day  → ~5-minute intervals
        - 2–90 days → hourly intervals
        - 91+ days → daily intervals

        The ``interval`` parameter can force "daily" granularity on Pro plans.

        Args:
            symbol: Ticker symbol (e.g. "BTC") or CoinGecko ID.
            days: Number of historical days to retrieve (1–max). Use "max"
                  via the string overload for full history (not supported here;
                  pass a large integer like 3650).
            vs_currency: Price denominator currency (default "usd").
            interval: Force "daily" granularity (Pro plan only). If ``None``
                      (default) CoinGecko selects granularity automatically.

        Returns:
            :class:`~models.market.HistoricalData` with OHLCV candles.
            Since CoinGecko market_chart does not expose open/high/low natively,
            this method uses the ``/ohlc`` endpoint when available (hourly
            buckets) or synthesises OHLCV from price/volume arrays.

        Raises:
            NotFoundError: If the coin is not found.
            ServiceError: For other API errors.

        Example::

            async with CoinGeckoService() as cg:
                hist = await cg.get_historical("BTC", days=30)
                print(hist.candles[-1].close)
        """
        coin_id = await self.resolve_coin_id(symbol)

        # Determine the interval label for the HistoricalData model
        if days <= 1:
            interval_label = "5m"
        elif days <= 90:
            interval_label = "1h"
        else:
            interval_label = "1d"

        params: Dict[str, Any] = {
            "vs_currency": vs_currency,
            "days": days,
        }
        if interval:
            params["interval"] = interval

        data = await self._make_request(
            method="GET",
            endpoint=f"/coins/{coin_id}/market_chart",
            params=params,
            cache_type=CacheType.HISTORICAL,
            cache_key_parts=["market_chart", coin_id, vs_currency, str(days)],
        )

        candles = self._parse_market_chart_to_ohlcv(data)

        return HistoricalData(
            symbol=symbol.upper(),
            asset_type=AssetType.CRYPTO,
            interval=interval_label,
            candles=candles,
            source=self.SERVICE_NAME,
        )

    async def get_ohlc(
        self,
        symbol: str,
        days: int = 30,
        vs_currency: str = _DEFAULT_VS_CURRENCY,
    ) -> HistoricalData:
        """
        Fetch true OHLC candles from CoinGecko's dedicated OHLC endpoint.

        The ``/coins/{id}/ohlc`` endpoint returns native 4-hour or daily candles
        (volume is not included — use :meth:`get_historical` if volume is needed).

        Available days: 1, 7, 14, 30, 90, 180, 365.

        Args:
            symbol: Ticker symbol or CoinGecko ID.
            days: Candle range. Snapped to nearest valid value.
            vs_currency: Price currency (default "usd").

        Returns:
            :class:`~models.market.HistoricalData` with OHLCV candles
            (volume set to 0.0 as it is not provided by this endpoint).

        Raises:
            NotFoundError: If the coin is not found.
            ServiceError: For other API errors.
        """
        coin_id = await self.resolve_coin_id(symbol)

        # Valid day values for the OHLC endpoint
        valid_days = [1, 7, 14, 30, 90, 180, 365]
        snapped_days = min(valid_days, key=lambda d: abs(d - days))

        interval_label = "4h" if snapped_days <= 30 else "1d"

        data = await self._make_request(
            method="GET",
            endpoint=f"/coins/{coin_id}/ohlc",
            params={
                "vs_currency": vs_currency,
                "days": snapped_days,
            },
            cache_type=CacheType.HISTORICAL,
            cache_key_parts=["ohlc", coin_id, vs_currency, str(snapped_days)],
        )

        # OHLC response: [[timestamp_ms, open, high, low, close], ...]
        candles: List[OHLCV] = []
        for row in data or []:
            if len(row) < 5:
                continue
            try:
                candles.append(
                    OHLCV(
                        timestamp=datetime.fromtimestamp(
                            row[0] / 1000, tz=timezone.utc
                        ),
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=0.0,  # OHLC endpoint does not include volume
                    )
                )
            except (TypeError, ValueError, IndexError):
                continue

        return HistoricalData(
            symbol=symbol.upper(),
            asset_type=AssetType.CRYPTO,
            interval=interval_label,
            candles=candles,
            source=self.SERVICE_NAME,
        )

    # ------------------------------------------------------------------
    # Coin search
    # ------------------------------------------------------------------

    async def search_coins(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for cryptocurrencies by name or ticker symbol.

        Args:
            query: Search string (e.g. "bitcoin" or "BTC").

        Returns:
            List of matching coin dictionaries, each containing:
            ``id``, ``name``, ``symbol``, ``market_cap_rank``, ``thumb``.

        Raises:
            ServiceError: If the search request fails.
        """
        data = await self._make_request(
            method="GET",
            endpoint="/search",
            params={"query": query},
            cache_type=CacheType.FUNDAMENTAL,
            cache_key_parts=["search", query.lower()],
        )

        coins = data.get("coins", []) if isinstance(data, dict) else []
        return [
            {
                "id": c.get("id", ""),
                "name": c.get("name", ""),
                "symbol": c.get("symbol", "").upper(),
                "market_cap_rank": c.get("market_cap_rank"),
                "thumb": c.get("thumb"),
            }
            for c in coins
        ]

    # ------------------------------------------------------------------
    # Internal parsers
    # ------------------------------------------------------------------

    def _parse_market_item_to_quote(
        self, symbol: str, item: Dict[str, Any]
    ) -> Quote:
        """
        Transform a ``/coins/markets`` list item into a :class:`~models.market.Quote`.

        Args:
            symbol: The user-supplied symbol (used as Quote.symbol).
            item: Single element from the CoinGecko /coins/markets response.

        Returns:
            Populated Quote instance.

        Raises:
            ValueError: If required fields are missing or unparseable.
        """
        price = float(item["current_price"] or 0)
        price_change_24h = float(item.get("price_change_24h") or 0)
        price_change_pct = float(
            item.get("price_change_percentage_24h") or 0
        )

        # Derive previous close from current price and 24h change
        previous_close: Optional[float] = None
        if price_change_24h is not None:
            try:
                previous_close = round(price - price_change_24h, 10)
            except (TypeError, ValueError):
                pass

        # Parse last_updated timestamp
        last_updated_raw = item.get("last_updated")
        if last_updated_raw:
            try:
                ts = datetime.fromisoformat(
                    last_updated_raw.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                ts = datetime.now(tz=timezone.utc)
        else:
            ts = datetime.now(tz=timezone.utc)

        return Quote(
            symbol=symbol.upper(),
            asset_type=AssetType.CRYPTO,
            price=price,
            change=price_change_24h,
            change_percent=price_change_pct,
            volume=float(item["total_volume"]) if item.get("total_volume") else None,
            market_cap=float(item["market_cap"]) if item.get("market_cap") else None,
            high_24h=float(item["high_24h"]) if item.get("high_24h") else None,
            low_24h=float(item["low_24h"]) if item.get("low_24h") else None,
            open_price=None,  # CoinGecko markets does not expose open price
            previous_close=previous_close,
            timestamp=ts,
            source=self.SERVICE_NAME,
        )

    def _parse_market_item_to_dict(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Flatten a ``/coins/markets`` item into a plain dictionary.

        Args:
            item: Single element from the CoinGecko /coins/markets response.

        Returns:
            Normalised market data dictionary.
        """
        return {
            "id": item.get("id", ""),
            "symbol": (item.get("symbol") or "").upper(),
            "name": item.get("name", ""),
            "image": item.get("image"),
            "current_price": item.get("current_price"),
            "market_cap": item.get("market_cap"),
            "market_cap_rank": item.get("market_cap_rank"),
            "fully_diluted_valuation": item.get("fully_diluted_valuation"),
            "total_volume": item.get("total_volume"),
            "high_24h": item.get("high_24h"),
            "low_24h": item.get("low_24h"),
            "price_change_24h": item.get("price_change_24h"),
            "price_change_percentage_24h": item.get("price_change_percentage_24h"),
            "price_change_percentage_7d": item.get(
                "price_change_percentage_7d_in_currency"
            ),
            "price_change_percentage_30d": item.get(
                "price_change_percentage_30d_in_currency"
            ),
            "market_cap_change_24h": item.get("market_cap_change_24h"),
            "market_cap_change_percentage_24h": item.get(
                "market_cap_change_percentage_24h"
            ),
            "circulating_supply": item.get("circulating_supply"),
            "total_supply": item.get("total_supply"),
            "max_supply": item.get("max_supply"),
            "ath": item.get("ath"),
            "ath_change_percentage": item.get("ath_change_percentage"),
            "ath_date": item.get("ath_date"),
            "atl": item.get("atl"),
            "atl_change_percentage": item.get("atl_change_percentage"),
            "atl_date": item.get("atl_date"),
            "last_updated": item.get("last_updated"),
        }

    def _parse_market_chart_to_ohlcv(
        self, data: Dict[str, Any]
    ) -> List[OHLCV]:
        """
        Convert a ``/coins/{id}/market_chart`` response to OHLCV candles.

        CoinGecko's market_chart endpoint returns separate ``prices``,
        ``market_caps``, and ``total_volumes`` arrays of ``[timestamp_ms, value]``
        pairs. This method aligns them by timestamp index and synthesises
        OHLCV candles (open = previous close; high = max of open/close;
        low = min of open/close) since true intra-candle OHLC is not available.

        Args:
            data: Raw JSON dict from the /market_chart endpoint.

        Returns:
            List of :class:`~models.market.OHLCV` candles, oldest first.
        """
        prices: List[List[float]] = data.get("prices", [])
        volumes: List[List[float]] = data.get("total_volumes", [])

        # Build a timestamp→volume lookup for alignment
        vol_by_ts: Dict[int, float] = {
            int(v[0]): float(v[1]) for v in volumes if len(v) >= 2
        }

        candles: List[OHLCV] = []
        prev_close: Optional[float] = None

        for i, price_point in enumerate(prices):
            if len(price_point) < 2:
                continue
            try:
                ts_ms = int(price_point[0])
                close = float(price_point[1])
            except (TypeError, ValueError):
                continue

            ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            open_price = prev_close if prev_close is not None else close
            high = max(open_price, close)
            low = min(open_price, close)
            volume = vol_by_ts.get(ts_ms, 0.0)

            candles.append(
                OHLCV(
                    timestamp=ts,
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                )
            )
            prev_close = close

        return candles
