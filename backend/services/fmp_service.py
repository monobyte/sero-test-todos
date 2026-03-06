"""
Financial Modeling Prep (FMP) service for fundamental financial data.

FMP provides:
- Company profiles and descriptions
- Income statements, balance sheets, cash-flow statements
- Financial ratios and key metrics
- SEC filings (EDGAR links)
- Real-time and historical price data

API documentation: https://financialmodelingprep.com/developer/docs/

FREE TIER LIMITS (2026):
  - 250 API calls per day
  - Most fundamental endpoints are free on the demo tier
  - Real-time quotes and some premium endpoints require a paid plan

AUTHENTICATION:
  All requests include ``?apikey={key}`` as a query parameter.
  Set FMP_API_KEY in your .env file.

RATE LIMIT STRATEGY:
  FMP's 250 calls/day limit is tight. The cache layer is critical:
  - Company profiles  → cached 24 h (fundamentals TTL)
  - Financial statements → cached 24 h (updated quarterly at most)
  - SEC filings       → cached 24 h
  Staying within budget even with active monitoring.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from config import settings
from models.fundamental import (
    BalanceSheet,
    CashFlowStatement,
    CompanyFundamentals,
    CompanyProfile,
    FinancialRatios,
    IncomeStatement,
    KeyMetrics,
    SECFiling,
)
from models.market import AssetType, HistoricalData, OHLCV, Quote
from services.base import (
    AuthenticationError,
    BaseService,
    CacheType,
    NotFoundError,
    ServiceError,
)
from utils.logger import get_logger

logger = get_logger(__name__)

# FMP base URL
_FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"


class FMPService(BaseService):
    """
    Service for Financial Modeling Prep (FMP) fundamental data.

    Primary use case: fetching company financials (income statements,
    balance sheets, cash-flow, ratios, key metrics) and SEC filings.
    Also supports basic quote and historical price fetching as a tertiary
    fallback behind Finnhub and yfinance.

    Usage::

        async with FMPService() as svc:
            profile = await svc.get_company_profile("AAPL")
            fundamentals = await svc.get_fundamentals("AAPL", period="annual", limit=4)
    """

    SERVICE_NAME = "fmp"
    REQUEST_TIMEOUT = 30.0
    MAX_RETRIES = 3
    RETRY_BACKOFF_FACTOR = 2.0

    # FMP returns a 401-like error body (not a true HTTP 401) when the API key
    # is invalid. The HTTP status is 200 but the body contains "Invalid API KEY".
    _INVALID_KEY_MARKERS = frozenset(
        {"Invalid API KEY", "Upgrade your plan", "Access restricted"}
    )

    # ------------------------------------------------------------------ #
    # BaseService abstract method implementations                          #
    # ------------------------------------------------------------------ #

    def _get_base_url(self) -> str:
        """FMP REST API base URL (v3)."""
        return _FMP_BASE_URL

    def _get_api_key(self) -> str:
        """Return FMP API key from application settings."""
        return settings.fmp_api_key

    # ------------------------------------------------------------------ #
    # Public API — fundamentals                                            #
    # ------------------------------------------------------------------ #

    async def get_company_profile(self, symbol: str) -> CompanyProfile:
        """
        Fetch company profile and basic info.

        Endpoint: ``GET /profile/{symbol}``

        Args:
            symbol: Ticker symbol (e.g. "AAPL").

        Returns:
            CompanyProfile with available fields.

        Raises:
            NotFoundError:       Symbol not found.
            AuthenticationError: Invalid or missing API key.
            ServiceError:        Other FMP API error.
        """
        symbol = symbol.upper()
        data = await self._fmp_get(
            endpoint=f"/profile/{symbol}",
            cache_type=CacheType.FUNDAMENTAL,
            cache_key_parts=["profile", symbol],
        )

        if not data or not isinstance(data, list) or len(data) == 0:
            raise NotFoundError(
                self.SERVICE_NAME,
                symbol,
                message=f"No company profile found for '{symbol}'.",
            )

        return self._parse_profile(data[0])

    async def get_income_statements(
        self,
        symbol: str,
        period: str = "annual",
        limit: int = 4,
    ) -> List[IncomeStatement]:
        """
        Fetch income statements for a symbol.

        Endpoint: ``GET /income-statement/{symbol}``

        Args:
            symbol: Ticker symbol.
            period: ``"annual"`` or ``"quarter"`` (default ``"annual"``).
            limit:  Number of periods to return (default 4 = 4 years annual).

        Returns:
            List of IncomeStatement objects (most recent first).
        """
        symbol = symbol.upper()
        data = await self._fmp_get(
            endpoint=f"/income-statement/{symbol}",
            params={"period": period, "limit": limit},
            cache_type=CacheType.FUNDAMENTAL,
            cache_key_parts=["income", symbol, period, str(limit)],
        )

        if not data or not isinstance(data, list):
            return []

        return [self._parse_income_statement(row) for row in data]

    async def get_balance_sheets(
        self,
        symbol: str,
        period: str = "annual",
        limit: int = 4,
    ) -> List[BalanceSheet]:
        """
        Fetch balance sheets for a symbol.

        Endpoint: ``GET /balance-sheet-statement/{symbol}``

        Args:
            symbol: Ticker symbol.
            period: ``"annual"`` or ``"quarter"`` (default ``"annual"``).
            limit:  Number of periods to return.

        Returns:
            List of BalanceSheet objects (most recent first).
        """
        symbol = symbol.upper()
        data = await self._fmp_get(
            endpoint=f"/balance-sheet-statement/{symbol}",
            params={"period": period, "limit": limit},
            cache_type=CacheType.FUNDAMENTAL,
            cache_key_parts=["balance", symbol, period, str(limit)],
        )

        if not data or not isinstance(data, list):
            return []

        return [self._parse_balance_sheet(row) for row in data]

    async def get_cash_flow_statements(
        self,
        symbol: str,
        period: str = "annual",
        limit: int = 4,
    ) -> List[CashFlowStatement]:
        """
        Fetch cash flow statements for a symbol.

        Endpoint: ``GET /cash-flow-statement/{symbol}``

        Args:
            symbol: Ticker symbol.
            period: ``"annual"`` or ``"quarter"`` (default ``"annual"``).
            limit:  Number of periods to return.

        Returns:
            List of CashFlowStatement objects (most recent first).
        """
        symbol = symbol.upper()
        data = await self._fmp_get(
            endpoint=f"/cash-flow-statement/{symbol}",
            params={"period": period, "limit": limit},
            cache_type=CacheType.FUNDAMENTAL,
            cache_key_parts=["cashflow", symbol, period, str(limit)],
        )

        if not data or not isinstance(data, list):
            return []

        return [self._parse_cash_flow(row) for row in data]

    async def get_financial_ratios(
        self,
        symbol: str,
        period: str = "annual",
        limit: int = 4,
    ) -> List[FinancialRatios]:
        """
        Fetch financial ratios for a symbol.

        Endpoint: ``GET /ratios/{symbol}``

        Args:
            symbol: Ticker symbol.
            period: ``"annual"`` or ``"quarter"`` (default ``"annual"``).
            limit:  Number of periods to return.

        Returns:
            List of FinancialRatios objects (most recent first).
        """
        symbol = symbol.upper()
        data = await self._fmp_get(
            endpoint=f"/ratios/{symbol}",
            params={"period": period, "limit": limit},
            cache_type=CacheType.FUNDAMENTAL,
            cache_key_parts=["ratios", symbol, period, str(limit)],
        )

        if not data or not isinstance(data, list):
            return []

        return [self._parse_ratios(row) for row in data]

    async def get_key_metrics(
        self,
        symbol: str,
        period: str = "annual",
        limit: int = 4,
    ) -> List[KeyMetrics]:
        """
        Fetch key financial metrics for a symbol.

        Endpoint: ``GET /key-metrics/{symbol}``

        Args:
            symbol: Ticker symbol.
            period: ``"annual"`` or ``"quarter"`` (default ``"annual"``).
            limit:  Number of periods to return.

        Returns:
            List of KeyMetrics objects (most recent first).
        """
        symbol = symbol.upper()
        data = await self._fmp_get(
            endpoint=f"/key-metrics/{symbol}",
            params={"period": period, "limit": limit},
            cache_type=CacheType.FUNDAMENTAL,
            cache_key_parts=["metrics", symbol, period, str(limit)],
        )

        if not data or not isinstance(data, list):
            return []

        return [self._parse_key_metrics(row) for row in data]

    async def get_sec_filings(
        self,
        symbol: str,
        filing_type: Optional[str] = None,
        limit: int = 20,
    ) -> List[SECFiling]:
        """
        Fetch SEC filings metadata for a symbol.

        Endpoint: ``GET /sec_filings/{symbol}``

        Args:
            symbol:      Ticker symbol.
            filing_type: Optional filter — e.g. ``"10-K"`` or ``"10-Q"``.
            limit:       Max number of filings to return (default 20).

        Returns:
            List of SECFiling objects (most recent first).
        """
        symbol = symbol.upper()
        params: Dict[str, Any] = {"limit": limit}
        if filing_type:
            params["type"] = filing_type

        key_parts = ["sec", symbol, filing_type or "all", str(limit)]
        data = await self._fmp_get(
            endpoint=f"/sec_filings/{symbol}",
            params=params,
            cache_type=CacheType.FUNDAMENTAL,
            cache_key_parts=key_parts,
        )

        if not data or not isinstance(data, list):
            return []

        return [self._parse_sec_filing(symbol, row) for row in data]

    async def get_fundamentals(
        self,
        symbol: str,
        period: str = "annual",
        limit: int = 4,
        include_sec_filings: bool = True,
    ) -> CompanyFundamentals:
        """
        Fetch all fundamental data for a symbol in a single call.

        Makes parallel requests for: profile, income statements, balance
        sheets, cash-flow statements, ratios, key metrics, and (optionally)
        SEC filings. Results are cached individually so repeated partial
        calls benefit from the cache.

        Args:
            symbol:              Ticker symbol.
            period:              ``"annual"`` or ``"quarter"``.
            limit:               Periods to fetch for each statement type.
            include_sec_filings: Whether to fetch SEC filings (costs 1 extra API call).

        Returns:
            CompanyFundamentals aggregating all available data.

        Raises:
            NotFoundError: Symbol not found.
            ServiceError:  API error.
        """
        symbol = symbol.upper()

        import asyncio as _asyncio

        # Fire off parallel requests — profile is mandatory; rest degrade gracefully
        tasks = [
            self.get_company_profile(symbol),
            self.get_income_statements(symbol, period=period, limit=limit),
            self.get_balance_sheets(symbol, period=period, limit=limit),
            self.get_cash_flow_statements(symbol, period=period, limit=limit),
            self.get_financial_ratios(symbol, period=period, limit=limit),
            self.get_key_metrics(symbol, period=period, limit=limit),
        ]
        if include_sec_filings:
            tasks.append(self.get_sec_filings(symbol, limit=10))

        results = await _asyncio.gather(*tasks, return_exceptions=True)

        # Unpack results — propagate NotFoundError from profile; suppress others
        profile_result = results[0]
        if isinstance(profile_result, Exception):
            raise profile_result

        def _safe_list(result: Any) -> list:
            if isinstance(result, Exception):
                self._logger.warning(
                    "fundamentals_partial_failure",
                    service=self.SERVICE_NAME,
                    symbol=symbol,
                    error=str(result),
                )
                return []
            return result if isinstance(result, list) else []

        income = _safe_list(results[1])
        balance = _safe_list(results[2])
        cash_flow = _safe_list(results[3])
        ratios = _safe_list(results[4])
        metrics = _safe_list(results[5])
        filings = _safe_list(results[6]) if include_sec_filings and len(results) > 6 else []

        self._logger.info(
            "fundamentals_fetched",
            service=self.SERVICE_NAME,
            symbol=symbol,
            income_periods=len(income),
            balance_periods=len(balance),
            cash_flow_periods=len(cash_flow),
        )

        return CompanyFundamentals(
            symbol=symbol,
            profile=profile_result,
            income_statements=income,
            balance_sheets=balance,
            cash_flow_statements=cash_flow,
            financial_ratios=ratios,
            key_metrics=metrics,
            sec_filings=filings,
            source=self.SERVICE_NAME,
            fetched_at=datetime.utcnow(),
        )

    # ------------------------------------------------------------------ #
    # Public API — quotes and historical (tertiary fallback)               #
    # ------------------------------------------------------------------ #

    async def get_quote(self, symbol: str) -> Quote:
        """
        Fetch a real-time quote via FMP.

        Endpoint: ``GET /quote/{symbol}``

        Note: Real-time quotes require an active FMP subscription on many
        exchanges. Free-tier returns delayed or last-trade data.

        Args:
            symbol: Ticker symbol.

        Returns:
            Quote model.

        Raises:
            NotFoundError: Symbol not found.
        """
        symbol = symbol.upper()
        data = await self._fmp_get(
            endpoint=f"/quote/{symbol}",
            cache_type=CacheType.QUOTE,
            cache_key_parts=["quote", symbol],
        )

        if not data or not isinstance(data, list) or len(data) == 0:
            raise NotFoundError(
                self.SERVICE_NAME,
                symbol,
                message=f"No quote data found for '{symbol}'.",
            )

        return self._parse_quote(data[0])

    async def get_historical(
        self,
        symbol: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> HistoricalData:
        """
        Fetch daily historical OHLCV prices via FMP.

        Endpoint: ``GET /historical-price-full/{symbol}``

        Args:
            symbol:    Ticker symbol.
            from_date: Start date (YYYY-MM-DD). Defaults to ~1 year ago.
            to_date:   End date (YYYY-MM-DD). Defaults to today.

        Returns:
            HistoricalData with daily candles.

        Raises:
            NotFoundError: Symbol not found or no historical data.
        """
        symbol = symbol.upper()
        params: Dict[str, Any] = {}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        key_parts = ["historical", symbol, from_date or "", to_date or ""]
        data = await self._fmp_get(
            endpoint=f"/historical-price-full/{symbol}",
            params=params or None,
            cache_type=CacheType.HISTORICAL,
            cache_key_parts=key_parts,
        )

        # FMP wraps candles in {"symbol": ..., "historical": [...]}
        if not data or not isinstance(data, dict):
            raise NotFoundError(
                self.SERVICE_NAME,
                symbol,
                message=f"No historical data found for '{symbol}'.",
            )

        raw_candles = data.get("historical", [])
        if not raw_candles:
            raise NotFoundError(
                self.SERVICE_NAME,
                symbol,
                message=f"Empty historical data returned for '{symbol}'.",
            )

        candles: List[OHLCV] = []
        for row in raw_candles:
            try:
                candles.append(
                    OHLCV(
                        timestamp=datetime.fromisoformat(row["date"]),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row.get("volume", 0.0)),
                    )
                )
            except (KeyError, ValueError) as exc:
                self._logger.warning(
                    "candle_parse_error",
                    service=self.SERVICE_NAME,
                    symbol=symbol,
                    row=row,
                    error=str(exc),
                )

        # FMP returns newest-first; reverse to chronological order
        candles.reverse()

        return HistoricalData(
            symbol=symbol,
            asset_type=AssetType.STOCK,
            interval="1d",
            candles=candles,
            source=self.SERVICE_NAME,
        )

    # ------------------------------------------------------------------ #
    # Private helpers — HTTP layer                                         #
    # ------------------------------------------------------------------ #

    async def _fmp_get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        cache_type: Optional[CacheType] = None,
        cache_key_parts: Optional[List[str]] = None,
    ) -> Any:
        """
        Make an authenticated GET request to the FMP API.

        Injects the ``apikey`` query parameter automatically.

        Args:
            endpoint:        API path (e.g. ``"/profile/AAPL"``).
            params:          Additional query parameters.
            cache_type:      Cache tier to use (or None to skip caching).
            cache_key_parts: Parts for building the cache key.

        Returns:
            Parsed JSON response (dict, list, or scalar).

        Raises:
            AuthenticationError: API key missing or invalid.
            ServiceError:        Other API-level error.
        """
        api_key = self._get_api_key()
        if not api_key:
            raise AuthenticationError(
                self.SERVICE_NAME,
                message=(
                    "FMP API key is not configured. "
                    "Set FMP_API_KEY in your .env file."
                ),
            )

        # Merge apikey into params
        merged_params: Dict[str, Any] = {"apikey": api_key}
        if params:
            merged_params.update(params)

        raw = await self._make_request(
            method="GET",
            endpoint=endpoint,
            params=merged_params,
            cache_type=cache_type,
            cache_key_parts=cache_key_parts,
        )

        # FMP sometimes returns HTTP 200 with an error body
        self._check_fmp_error(raw, endpoint)
        return raw

    def _check_fmp_error(self, data: Any, endpoint: str) -> None:
        """
        Detect FMP-specific error payloads returned with HTTP 200.

        FMP occasionally wraps errors as::

            {"Error Message": "Invalid API KEY ..."}
            {"message": "Upgrade your plan ..."}

        Args:
            data:     Parsed JSON response.
            endpoint: Endpoint path (for logging).

        Raises:
            AuthenticationError: API key invalid or quota exceeded.
            ServiceError:        Other FMP-specific error.
        """
        if not isinstance(data, dict):
            return

        error_msg: Optional[str] = data.get("Error Message") or data.get("message")
        if not error_msg:
            return

        for marker in self._INVALID_KEY_MARKERS:
            if marker.lower() in error_msg.lower():
                self._logger.error(
                    "fmp_auth_error",
                    service=self.SERVICE_NAME,
                    endpoint=endpoint,
                    message=error_msg,
                )
                raise AuthenticationError(
                    self.SERVICE_NAME,
                    message=f"FMP authentication error: {error_msg}",
                )

        self._logger.error(
            "fmp_api_error",
            service=self.SERVICE_NAME,
            endpoint=endpoint,
            message=error_msg,
        )
        raise ServiceError(
            message=f"FMP API error: {error_msg}",
            service=self.SERVICE_NAME,
        )

    # ------------------------------------------------------------------ #
    # Private helpers — response parsers                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _opt_float(data: Dict[str, Any], key: str) -> Optional[float]:
        """Safely extract an optional float from an API response dict."""
        val = data.get(key)
        if val is None or val == "":
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _opt_int(data: Dict[str, Any], key: str) -> Optional[int]:
        """Safely extract an optional int from an API response dict."""
        val = data.get(key)
        if val is None or val == "":
            return None
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _opt_str(data: Dict[str, Any], key: str) -> Optional[str]:
        """Safely extract an optional non-empty string from an API response dict."""
        val = data.get(key)
        return str(val) if val else None

    def _parse_profile(self, data: Dict[str, Any]) -> CompanyProfile:
        """Parse a raw FMP /profile response into CompanyProfile."""
        return CompanyProfile(
            symbol=data.get("symbol", ""),
            company_name=data.get("companyName", ""),
            exchange=data.get("exchangeShortName") or data.get("exchange", ""),
            sector=self._opt_str(data, "sector"),
            industry=self._opt_str(data, "industry"),
            description=self._opt_str(data, "description"),
            ceo=self._opt_str(data, "ceo"),
            website=self._opt_str(data, "website"),
            country=self._opt_str(data, "country"),
            employees=self._opt_int(data, "fullTimeEmployees"),
            currency=data.get("currency", "USD"),
            market_cap=self._opt_float(data, "mktCap"),
            beta=self._opt_float(data, "beta"),
            price=self._opt_float(data, "price"),
            avg_volume=self._opt_float(data, "volAvg"),
            ipo_date=self._opt_str(data, "ipoDate"),
            image=self._opt_str(data, "image"),
            is_etf=bool(data.get("isEtf", False)),
            is_actively_trading=bool(data.get("isActivelyTrading", True)),
            source=self.SERVICE_NAME,
        )

    def _parse_income_statement(self, data: Dict[str, Any]) -> IncomeStatement:
        """Parse a raw FMP income-statement row."""
        return IncomeStatement(
            symbol=data.get("symbol", ""),
            date=data.get("date", ""),
            period=data.get("period", "annual"),
            calendar_year=self._opt_str(data, "calendarYear"),
            currency=data.get("reportedCurrency", "USD"),
            revenue=self._opt_float(data, "revenue"),
            cost_of_revenue=self._opt_float(data, "costOfRevenue"),
            gross_profit=self._opt_float(data, "grossProfit"),
            gross_profit_ratio=self._opt_float(data, "grossProfitRatio"),
            research_and_development_expenses=self._opt_float(
                data, "researchAndDevelopmentExpenses"
            ),
            selling_general_and_administrative_expenses=self._opt_float(
                data, "sellingGeneralAndAdministrativeExpenses"
            ),
            operating_expenses=self._opt_float(data, "operatingExpenses"),
            operating_income=self._opt_float(data, "operatingIncome"),
            operating_income_ratio=self._opt_float(data, "operatingIncomeRatio"),
            interest_expense=self._opt_float(data, "interestExpense"),
            income_before_tax=self._opt_float(data, "incomeBeforeTax"),
            income_tax_expense=self._opt_float(data, "incomeTaxExpense"),
            net_income=self._opt_float(data, "netIncome"),
            net_income_ratio=self._opt_float(data, "netIncomeRatio"),
            eps=self._opt_float(data, "eps"),
            eps_diluted=self._opt_float(data, "epsdiluted"),
            weighted_average_shares=self._opt_float(data, "weightedAverageShsOut"),
            weighted_average_shares_diluted=self._opt_float(data, "weightedAverageShsOutDil"),
            ebitda=self._opt_float(data, "ebitda"),
            depreciation_and_amortization=self._opt_float(data, "depreciationAndAmortization"),
            source=self.SERVICE_NAME,
        )

    def _parse_balance_sheet(self, data: Dict[str, Any]) -> BalanceSheet:
        """Parse a raw FMP balance-sheet row."""
        return BalanceSheet(
            symbol=data.get("symbol", ""),
            date=data.get("date", ""),
            period=data.get("period", "annual"),
            calendar_year=self._opt_str(data, "calendarYear"),
            currency=data.get("reportedCurrency", "USD"),
            cash_and_equivalents=self._opt_float(data, "cashAndCashEquivalents"),
            short_term_investments=self._opt_float(data, "shortTermInvestments"),
            net_receivables=self._opt_float(data, "netReceivables"),
            inventory=self._opt_float(data, "inventory"),
            total_current_assets=self._opt_float(data, "totalCurrentAssets"),
            property_plant_equipment_net=self._opt_float(data, "propertyPlantEquipmentNet"),
            goodwill=self._opt_float(data, "goodwill"),
            intangible_assets=self._opt_float(data, "intangibleAssets"),
            total_non_current_assets=self._opt_float(data, "totalNonCurrentAssets"),
            total_assets=self._opt_float(data, "totalAssets"),
            accounts_payable=self._opt_float(data, "accountPayables"),
            short_term_debt=self._opt_float(data, "shortTermDebt"),
            total_current_liabilities=self._opt_float(data, "totalCurrentLiabilities"),
            long_term_debt=self._opt_float(data, "longTermDebt"),
            total_non_current_liabilities=self._opt_float(data, "totalNonCurrentLiabilities"),
            total_liabilities=self._opt_float(data, "totalLiabilities"),
            retained_earnings=self._opt_float(data, "retainedEarnings"),
            total_stockholders_equity=self._opt_float(data, "totalStockholdersEquity"),
            total_liabilities_and_equity=self._opt_float(
                data, "totalLiabilitiesAndStockholdersEquity"
            ),
            total_debt=self._opt_float(data, "totalDebt"),
            net_debt=self._opt_float(data, "netDebt"),
            source=self.SERVICE_NAME,
        )

    def _parse_cash_flow(self, data: Dict[str, Any]) -> CashFlowStatement:
        """Parse a raw FMP cash-flow statement row."""
        return CashFlowStatement(
            symbol=data.get("symbol", ""),
            date=data.get("date", ""),
            period=data.get("period", "annual"),
            calendar_year=self._opt_str(data, "calendarYear"),
            currency=data.get("reportedCurrency", "USD"),
            net_income=self._opt_float(data, "netIncome"),
            depreciation_and_amortization=self._opt_float(data, "depreciationAndAmortization"),
            stock_based_compensation=self._opt_float(data, "stockBasedCompensation"),
            change_in_working_capital=self._opt_float(data, "changeInWorkingCapital"),
            operating_cash_flow=self._opt_float(data, "netCashProvidedByOperatingActivities"),
            capital_expenditure=self._opt_float(data, "capitalExpenditure"),
            acquisitions=self._opt_float(data, "acquisitionsNet"),
            purchases_of_investments=self._opt_float(data, "purchasesOfInvestments"),
            sales_of_investments=self._opt_float(data, "salesMaturitiesOfInvestments"),
            investing_cash_flow=self._opt_float(data, "netCashUsedForInvestingActivites"),
            debt_repayment=self._opt_float(data, "debtRepayment"),
            common_stock_issued=self._opt_float(data, "commonStockIssued"),
            common_stock_repurchased=self._opt_float(data, "commonStockRepurchased"),
            dividends_paid=self._opt_float(data, "dividendsPaid"),
            financing_cash_flow=self._opt_float(
                data, "netCashUsedProvidedByFinancingActivities"
            ),
            net_change_in_cash=self._opt_float(data, "netChangeInCash"),
            free_cash_flow=self._opt_float(data, "freeCashFlow"),
            source=self.SERVICE_NAME,
        )

    def _parse_ratios(self, data: Dict[str, Any]) -> FinancialRatios:
        """Parse a raw FMP /ratios row."""
        return FinancialRatios(
            symbol=data.get("symbol", ""),
            date=data.get("date", ""),
            period=data.get("period", "annual"),
            calendar_year=self._opt_str(data, "calendarYear"),
            current_ratio=self._opt_float(data, "currentRatio"),
            quick_ratio=self._opt_float(data, "quickRatio"),
            cash_ratio=self._opt_float(data, "cashRatio"),
            gross_profit_margin=self._opt_float(data, "grossProfitMargin"),
            operating_profit_margin=self._opt_float(data, "operatingProfitMargin"),
            net_profit_margin=self._opt_float(data, "netProfitMargin"),
            return_on_equity=self._opt_float(data, "returnOnEquity"),
            return_on_assets=self._opt_float(data, "returnOnAssets"),
            return_on_capital_employed=self._opt_float(data, "returnOnCapitalEmployed"),
            price_earnings_ratio=self._opt_float(data, "priceEarningsRatio"),
            price_to_book_ratio=self._opt_float(data, "priceToBookRatio"),
            price_to_sales_ratio=self._opt_float(data, "priceToSalesRatio"),
            price_to_free_cash_flow=self._opt_float(data, "priceToFreeCashFlowsRatio"),
            ev_to_ebitda=self._opt_float(data, "enterpriseValueMultiple"),
            debt_equity_ratio=self._opt_float(data, "debtEquityRatio"),
            debt_ratio=self._opt_float(data, "debtRatio"),
            interest_coverage=self._opt_float(data, "interestCoverage"),
            asset_turnover=self._opt_float(data, "assetTurnover"),
            inventory_turnover=self._opt_float(data, "inventoryTurnover"),
            days_sales_outstanding=self._opt_float(data, "daysOfSalesOutstanding"),
            dividend_yield=self._opt_float(data, "dividendYield"),
            payout_ratio=self._opt_float(data, "payoutRatio"),
            earnings_yield=self._opt_float(data, "earningsYield"),
            free_cash_flow_yield=self._opt_float(data, "freeCashFlowYield"),
            source=self.SERVICE_NAME,
        )

    def _parse_key_metrics(self, data: Dict[str, Any]) -> KeyMetrics:
        """Parse a raw FMP /key-metrics row."""
        return KeyMetrics(
            symbol=data.get("symbol", ""),
            date=data.get("date", ""),
            period=data.get("period", "annual"),
            calendar_year=self._opt_str(data, "calendarYear"),
            currency=data.get("currency", "USD"),
            revenue_per_share=self._opt_float(data, "revenuePerShare"),
            net_income_per_share=self._opt_float(data, "netIncomePerShare"),
            operating_cash_flow_per_share=self._opt_float(data, "operatingCashFlowPerShare"),
            free_cash_flow_per_share=self._opt_float(data, "freeCashFlowPerShare"),
            cash_per_share=self._opt_float(data, "cashPerShare"),
            book_value_per_share=self._opt_float(data, "bookValuePerShare"),
            enterprise_value=self._opt_float(data, "enterpriseValue"),
            ev_to_sales=self._opt_float(data, "evToSales"),
            ev_to_ebitda=self._opt_float(data, "evToEbitda") or self._opt_float(
                data, "enterpriseValueOverEBITDA"
            ),
            ev_to_operating_cash_flow=self._opt_float(data, "evToOperatingCashFlow"),
            ev_to_free_cash_flow=self._opt_float(data, "evToFreeCashFlow"),
            pe_ratio=self._opt_float(data, "peRatio"),
            pb_ratio=self._opt_float(data, "pbRatio"),
            ps_ratio=self._opt_float(data, "psRatio") or self._opt_float(data, "priceToSalesRatio"),
            price_to_free_cash_flow=self._opt_float(data, "pfcfRatio"),
            debt_to_equity=self._opt_float(data, "debtToEquity"),
            debt_to_assets=self._opt_float(data, "debtToAssets"),
            net_debt_to_ebitda=self._opt_float(data, "netDebtToEBITDA"),
            roe=self._opt_float(data, "roe"),
            roa=self._opt_float(data, "returnOnTangibleAssets") or self._opt_float(data, "roa"),
            roic=self._opt_float(data, "roic"),
            dividend_yield=self._opt_float(data, "dividendYield"),
            dividend_per_share=self._opt_float(data, "dividendPerShare"),
            payout_ratio=self._opt_float(data, "payoutRatio"),
            source=self.SERVICE_NAME,
        )

    def _parse_sec_filing(self, symbol: str, data: Dict[str, Any]) -> SECFiling:
        """Parse a raw FMP SEC filing row."""
        return SECFiling(
            symbol=symbol,
            cik=self._opt_str(data, "cik"),
            filing_type=data.get("type", ""),
            accepted_date=self._opt_str(data, "acceptedDate"),
            filing_date=self._opt_str(data, "fillingDate"),
            link=self._opt_str(data, "link"),
            final_link=self._opt_str(data, "finalLink"),
            source=self.SERVICE_NAME,
        )

    def _parse_quote(self, data: Dict[str, Any]) -> Quote:
        """Parse a raw FMP /quote row."""
        price = self._opt_float(data, "price") or 0.0
        prev_close = self._opt_float(data, "previousClose") or 0.0
        change = self._opt_float(data, "change") or (price - prev_close)
        change_pct = self._opt_float(data, "changesPercentage") or (
            (change / prev_close * 100) if prev_close else 0.0
        )

        return Quote(
            symbol=data.get("symbol", ""),
            asset_type=AssetType.STOCK,
            price=price,
            change=round(change, 4),
            change_percent=round(change_pct, 4),
            volume=self._opt_float(data, "volume"),
            market_cap=self._opt_float(data, "marketCap"),
            high_24h=self._opt_float(data, "dayHigh"),
            low_24h=self._opt_float(data, "dayLow"),
            open_price=self._opt_float(data, "open"),
            previous_close=prev_close if prev_close else None,
            timestamp=datetime.utcnow(),
            source=self.SERVICE_NAME,
        )
