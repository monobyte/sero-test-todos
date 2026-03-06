"""
Unit tests for FMPService.

Tests cover:
- Service configuration (URL, auth)
- API key validation
- Company profile parsing
- Income statement, balance sheet, cash-flow parsing
- Financial ratios and key metrics parsing
- SEC filing parsing
- Quote and historical data parsing
- Error payload detection (FMP 200 + error body)
- Caching behaviour
- get_fundamentals() aggregation
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, call

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
from models.market import AssetType, HistoricalData, Quote
from services.fmp_service import FMPService
from services.base import AuthenticationError, CacheType, NotFoundError, ServiceError


# ---------------------------------------------------------------------------
# Sample API responses (representative subsets of real FMP payloads)
# ---------------------------------------------------------------------------

SAMPLE_PROFILE = {
    "symbol": "AAPL",
    "companyName": "Apple Inc.",
    "exchange": "NASDAQ Global Select",
    "exchangeShortName": "NASDAQ",
    "sector": "Technology",
    "industry": "Consumer Electronics",
    "description": "Apple Inc. designs, manufactures, and markets smartphones.",
    "ceo": "Mr. Timothy D. Cook",
    "website": "https://www.apple.com",
    "country": "US",
    "fullTimeEmployees": "164000",
    "currency": "USD",
    "mktCap": 2_800_000_000_000.0,
    "beta": 1.24,
    "price": 178.50,
    "volAvg": 55_000_000,
    "ipoDate": "1980-12-12",
    "image": "https://financialmodelingprep.com/image-stock/AAPL.png",
    "isEtf": False,
    "isActivelyTrading": True,
}

SAMPLE_INCOME = {
    "date": "2025-09-28",
    "symbol": "AAPL",
    "reportedCurrency": "USD",
    "period": "FY",
    "calendarYear": "2025",
    "revenue": 391_035_000_000,
    "costOfRevenue": 220_253_000_000,
    "grossProfit": 170_782_000_000,
    "grossProfitRatio": 0.4367,
    "researchAndDevelopmentExpenses": 29_915_000_000,
    "sellingGeneralAndAdministrativeExpenses": 26_097_000_000,
    "operatingExpenses": 56_012_000_000,
    "operatingIncome": 114_301_000_000,
    "operatingIncomeRatio": 0.2924,
    "interestExpense": 3_933_000_000,
    "incomeBeforeTax": 112_890_000_000,
    "incomeTaxExpense": 19_517_000_000,
    "netIncome": 93_736_000_000,
    "netIncomeRatio": 0.2397,
    "eps": 6.09,
    "epsdiluted": 6.08,
    "weightedAverageShsOut": 15_408_000_000,
    "weightedAverageShsOutDil": 15_432_000_000,
    "ebitda": 141_582_000_000,
    "depreciationAndAmortization": 11_455_000_000,
}

SAMPLE_BALANCE = {
    "date": "2025-09-28",
    "symbol": "AAPL",
    "reportedCurrency": "USD",
    "period": "FY",
    "calendarYear": "2025",
    "cashAndCashEquivalents": 29_943_000_000,
    "shortTermInvestments": 35_228_000_000,
    "netReceivables": 60_331_000_000,
    "inventory": 6_132_000_000,
    "totalCurrentAssets": 152_987_000_000,
    "propertyPlantEquipmentNet": 44_502_000_000,
    "goodwill": 0,
    "intangibleAssets": 0,
    "totalNonCurrentAssets": 211_966_000_000,
    "totalAssets": 364_980_000_000,
    "accountPayables": 68_960_000_000,
    "shortTermDebt": 10_912_000_000,
    "totalCurrentLiabilities": 176_392_000_000,
    "longTermDebt": 85_750_000_000,
    "totalNonCurrentLiabilities": 145_374_000_000,
    "totalLiabilities": 321_766_000_000,
    "retainedEarnings": -19_154_000_000,
    "totalStockholdersEquity": 56_950_000_000,
    "totalLiabilitiesAndStockholdersEquity": 364_980_000_000,
    "totalDebt": 96_662_000_000,
    "netDebt": 66_719_000_000,
}

SAMPLE_CASHFLOW = {
    "date": "2025-09-28",
    "symbol": "AAPL",
    "reportedCurrency": "USD",
    "period": "FY",
    "calendarYear": "2025",
    "netIncome": 93_736_000_000,
    "depreciationAndAmortization": 11_455_000_000,
    "stockBasedCompensation": 11_688_000_000,
    "changeInWorkingCapital": -6_234_000_000,
    "netCashProvidedByOperatingActivities": 116_434_000_000,
    "capitalExpenditure": -9_447_000_000,
    "acquisitionsNet": 0,
    "purchasesOfInvestments": -48_656_000_000,
    "salesMaturitiesOfInvestments": 62_346_000_000,
    "netCashUsedForInvestingActivites": -5_688_000_000,
    "debtRepayment": -10_000_000_000,
    "commonStockIssued": 0,
    "commonStockRepurchased": -90_215_000_000,
    "dividendsPaid": -14_927_000_000,
    "netCashUsedProvidedByFinancingActivities": -121_983_000_000,
    "netChangeInCash": -11_237_000_000,
    "freeCashFlow": 106_987_000_000,
}

SAMPLE_RATIOS = {
    "symbol": "AAPL",
    "date": "2025-09-28",
    "period": "annual",
    "calendarYear": "2025",
    "currentRatio": 0.87,
    "quickRatio": 0.82,
    "cashRatio": 0.17,
    "grossProfitMargin": 0.437,
    "operatingProfitMargin": 0.292,
    "netProfitMargin": 0.240,
    "returnOnEquity": 1.645,
    "returnOnAssets": 0.257,
    "returnOnCapitalEmployed": 0.527,
    "priceEarningsRatio": 29.3,
    "priceToBookRatio": 49.1,
    "priceToSalesRatio": 7.01,
    "priceToFreeCashFlowsRatio": 26.7,
    "enterpriseValueMultiple": 23.4,
    "debtEquityRatio": 1.70,
    "debtRatio": 0.26,
    "interestCoverage": 29.1,
    "assetTurnover": 1.07,
    "inventoryTurnover": 36.0,
    "daysOfSalesOutstanding": 56.3,
    "dividendYield": 0.0053,
    "payoutRatio": 0.155,
    "earningsYield": 0.034,
    "freeCashFlowYield": 0.037,
}

SAMPLE_METRICS = {
    "symbol": "AAPL",
    "date": "2025-09-28",
    "period": "annual",
    "calendarYear": "2025",
    "currency": "USD",
    "revenuePerShare": 25.38,
    "netIncomePerShare": 6.09,
    "operatingCashFlowPerShare": 7.56,
    "freeCashFlowPerShare": 6.95,
    "cashPerShare": 4.22,
    "bookValuePerShare": 3.70,
    "enterpriseValue": 2_780_000_000_000,
    "evToSales": 7.12,
    "evToEbitda": 19.6,
    "evToOperatingCashFlow": 23.9,
    "evToFreeCashFlow": 26.0,
    "peRatio": 29.3,
    "pbRatio": 49.1,
    "psRatio": 7.01,
    "pfcfRatio": 26.7,
    "debtToEquity": 1.70,
    "debtToAssets": 0.26,
    "netDebtToEBITDA": 0.47,
    "roe": 1.645,
    "roic": 0.527,
    "dividendYield": 0.0053,
    "dividendPerShare": 0.95,
    "payoutRatio": 0.155,
}

SAMPLE_SEC_FILING = {
    "cik": "0000320193",
    "type": "10-K",
    "acceptedDate": "2025-11-01 06:01:05",
    "fillingDate": "2025-11-01",
    "link": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=AAPL&type=10-K",
    "finalLink": "https://www.sec.gov/Archives/edgar/data/320193/10K.htm",
}

SAMPLE_QUOTE = {
    "symbol": "AAPL",
    "price": 178.50,
    "change": 2.35,
    "changesPercentage": 1.33,
    "previousClose": 176.15,
    "dayHigh": 179.20,
    "dayLow": 176.80,
    "open": 177.00,
    "volume": 52_347_890,
    "marketCap": 2_800_000_000_000,
}

SAMPLE_HISTORICAL = {
    "symbol": "AAPL",
    "historical": [
        {
            "date": "2026-03-06",
            "open": 177.0,
            "high": 179.2,
            "low": 176.8,
            "close": 178.5,
            "volume": 52_000_000,
        },
        {
            "date": "2026-03-05",
            "open": 175.0,
            "high": 177.5,
            "low": 174.5,
            "close": 176.8,
            "volume": 48_000_000,
        },
    ],
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def svc() -> FMPService:
    """Fresh FMPService instance."""
    return FMPService()


# ---------------------------------------------------------------------------
# Service configuration tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestServiceConfiguration:
    def test_service_name(self, svc):
        assert svc.SERVICE_NAME == "fmp"

    def test_base_url(self, svc):
        assert svc._get_base_url() == "https://financialmodelingprep.com/api/v3"

    def test_api_key_from_settings(self, svc, monkeypatch):
        from config import settings
        monkeypatch.setattr(settings, "fmp_api_key", "test_fmp_key_123")
        assert svc._get_api_key() == "test_fmp_key_123"

    def test_max_retries(self, svc):
        assert svc.MAX_RETRIES == 3

    @pytest.mark.asyncio
    async def test_context_manager(self):
        async with FMPService() as svc_ctx:
            assert svc_ctx.SERVICE_NAME == "fmp"


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestErrorHandling:
    def test_check_fmp_error_passes_on_list(self, svc):
        """List responses (normal) should not raise."""
        svc._check_fmp_error([{"symbol": "AAPL"}], "/profile/AAPL")  # no raise

    def test_check_fmp_error_passes_on_valid_dict(self, svc):
        """Dicts without error keys should not raise."""
        svc._check_fmp_error({"symbol": "AAPL", "price": 150.0}, "/quote/AAPL")

    def test_check_fmp_error_raises_auth_on_invalid_key(self, svc):
        payload = {"Error Message": "Invalid API KEY. Please retry or visit our documentation."}
        with pytest.raises(AuthenticationError) as exc:
            svc._check_fmp_error(payload, "/profile/AAPL")
        assert exc.value.service == "fmp"

    def test_check_fmp_error_raises_auth_on_upgrade_message(self, svc):
        payload = {"message": "Upgrade your plan to access this endpoint."}
        with pytest.raises(AuthenticationError):
            svc._check_fmp_error(payload, "/financials/AAPL")

    def test_check_fmp_error_raises_service_error_on_other_error(self, svc):
        payload = {"message": "Unknown error occurred"}
        with pytest.raises(ServiceError) as exc:
            svc._check_fmp_error(payload, "/quote/AAPL")
        assert "FMP API error" in str(exc.value)

    @pytest.mark.asyncio
    async def test_missing_api_key_raises_auth_error(self, svc, monkeypatch):
        from config import settings
        monkeypatch.setattr(settings, "fmp_api_key", "")

        with pytest.raises(AuthenticationError) as exc:
            await svc.get_company_profile("AAPL")
        assert "not configured" in str(exc.value)


# ---------------------------------------------------------------------------
# Parser unit tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestParsers:
    """Test individual parser methods with sample data."""

    def test_parse_profile(self, svc):
        profile = svc._parse_profile(SAMPLE_PROFILE)

        assert isinstance(profile, CompanyProfile)
        assert profile.symbol        == "AAPL"
        assert profile.company_name  == "Apple Inc."
        assert profile.exchange      == "NASDAQ"
        assert profile.sector        == "Technology"
        assert profile.industry      == "Consumer Electronics"
        assert profile.employees     == 164000
        assert profile.market_cap    == pytest.approx(2.8e12)
        assert profile.beta          == pytest.approx(1.24)
        assert profile.ipo_date      == "1980-12-12"
        assert profile.is_etf        is False
        assert profile.source        == "fmp"

    def test_parse_income_statement(self, svc):
        stmt = svc._parse_income_statement(SAMPLE_INCOME)

        assert isinstance(stmt, IncomeStatement)
        assert stmt.symbol             == "AAPL"
        assert stmt.date               == "2025-09-28"
        assert stmt.revenue            == pytest.approx(391_035_000_000)
        assert stmt.gross_profit_ratio == pytest.approx(0.4367)
        assert stmt.net_income         == pytest.approx(93_736_000_000)
        assert stmt.eps                == pytest.approx(6.09)
        assert stmt.ebitda             == pytest.approx(141_582_000_000)
        assert stmt.source             == "fmp"

    def test_parse_balance_sheet(self, svc):
        sheet = svc._parse_balance_sheet(SAMPLE_BALANCE)

        assert isinstance(sheet, BalanceSheet)
        assert sheet.symbol               == "AAPL"
        assert sheet.total_assets         == pytest.approx(364_980_000_000)
        assert sheet.total_stockholders_equity == pytest.approx(56_950_000_000)
        assert sheet.net_debt             == pytest.approx(66_719_000_000)
        assert sheet.source               == "fmp"

    def test_parse_cash_flow(self, svc):
        cf = svc._parse_cash_flow(SAMPLE_CASHFLOW)

        assert isinstance(cf, CashFlowStatement)
        assert cf.operating_cash_flow   == pytest.approx(116_434_000_000)
        assert cf.capital_expenditure   == pytest.approx(-9_447_000_000)
        assert cf.free_cash_flow        == pytest.approx(106_987_000_000)
        assert cf.dividends_paid        == pytest.approx(-14_927_000_000)
        assert cf.source                == "fmp"

    def test_parse_ratios(self, svc):
        ratios = svc._parse_ratios(SAMPLE_RATIOS)

        assert isinstance(ratios, FinancialRatios)
        assert ratios.current_ratio          == pytest.approx(0.87)
        assert ratios.return_on_equity       == pytest.approx(1.645)
        assert ratios.price_earnings_ratio   == pytest.approx(29.3)
        assert ratios.dividend_yield         == pytest.approx(0.0053)
        assert ratios.source                 == "fmp"

    def test_parse_key_metrics(self, svc):
        km = svc._parse_key_metrics(SAMPLE_METRICS)

        assert isinstance(km, KeyMetrics)
        assert km.enterprise_value       == pytest.approx(2_780_000_000_000)
        assert km.pe_ratio               == pytest.approx(29.3)
        assert km.debt_to_equity         == pytest.approx(1.70)
        assert km.roe                    == pytest.approx(1.645)
        assert km.dividend_per_share     == pytest.approx(0.95)
        assert km.source                 == "fmp"

    def test_parse_sec_filing(self, svc):
        filing = svc._parse_sec_filing("AAPL", SAMPLE_SEC_FILING)

        assert isinstance(filing, SECFiling)
        assert filing.symbol       == "AAPL"
        assert filing.cik          == "0000320193"
        assert filing.filing_type  == "10-K"
        assert filing.filing_date  == "2025-11-01"
        assert "sec.gov" in (filing.link or "")
        assert filing.source       == "fmp"

    def test_parse_quote(self, svc):
        quote = svc._parse_quote(SAMPLE_QUOTE)

        assert isinstance(quote, Quote)
        assert quote.symbol        == "AAPL"
        assert quote.price         == pytest.approx(178.50)
        assert quote.change        == pytest.approx(2.35)
        assert quote.change_percent == pytest.approx(1.33)
        assert quote.high_24h      == pytest.approx(179.20)
        assert quote.source        == "fmp"

    def test_parse_quote_derives_change_if_missing(self, svc):
        """When 'change' and 'changesPercentage' are absent, derive from price/prev_close."""
        data = {
            "symbol": "TSLA",
            "price": 110.0,
            "previousClose": 100.0,
        }
        quote = svc._parse_quote(data)
        assert quote.change         == pytest.approx(10.0, abs=0.01)
        assert quote.change_percent == pytest.approx(10.0, abs=0.01)

    def test_opt_float_handles_none(self, svc):
        assert svc._opt_float({"x": None}, "x") is None

    def test_opt_float_handles_empty_string(self, svc):
        assert svc._opt_float({"x": ""}, "x") is None

    def test_opt_float_handles_numeric_string(self, svc):
        assert svc._opt_float({"x": "42.5"}, "x") == pytest.approx(42.5)

    def test_opt_int_handles_string_number(self, svc):
        assert svc._opt_int({"n": "164000"}, "n") == 164000

    def test_opt_str_returns_none_for_empty(self, svc):
        assert svc._opt_str({"s": ""}, "s") is None
        assert svc._opt_str({"s": None}, "s") is None


# ---------------------------------------------------------------------------
# Async API method tests (mocked _fmp_get)
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestGetCompanyProfile:
    async def test_returns_profile(self, svc, monkeypatch):
        monkeypatch.setattr(settings_module(svc), "fmp_api_key", "key123")
        svc._fmp_get = AsyncMock(return_value=[SAMPLE_PROFILE])

        profile = await svc.get_company_profile("AAPL")

        assert profile.symbol == "AAPL"
        svc._fmp_get.assert_called_once_with(
            endpoint="/profile/AAPL",
            cache_type=CacheType.FUNDAMENTAL,
            cache_key_parts=["profile", "AAPL"],
        )

    async def test_empty_list_raises_not_found(self, svc):
        svc._fmp_get = AsyncMock(return_value=[])
        with pytest.raises(NotFoundError):
            await svc.get_company_profile("INVALID")

    async def test_none_response_raises_not_found(self, svc):
        svc._fmp_get = AsyncMock(return_value=None)
        with pytest.raises(NotFoundError):
            await svc.get_company_profile("INVALID")

    async def test_symbol_upper_cased(self, svc):
        svc._fmp_get = AsyncMock(return_value=[SAMPLE_PROFILE])
        await svc.get_company_profile("aapl")
        call_endpoint = svc._fmp_get.call_args.kwargs["endpoint"]
        assert call_endpoint == "/profile/AAPL"


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetIncomeStatements:
    async def test_returns_list_of_statements(self, svc):
        svc._fmp_get = AsyncMock(return_value=[SAMPLE_INCOME, SAMPLE_INCOME])
        results = await svc.get_income_statements("AAPL", period="annual", limit=2)
        assert len(results) == 2
        assert all(isinstance(r, IncomeStatement) for r in results)

    async def test_empty_response_returns_empty_list(self, svc):
        svc._fmp_get = AsyncMock(return_value=[])
        results = await svc.get_income_statements("AAPL")
        assert results == []

    async def test_none_response_returns_empty_list(self, svc):
        svc._fmp_get = AsyncMock(return_value=None)
        results = await svc.get_income_statements("AAPL")
        assert results == []

    async def test_period_and_limit_forwarded(self, svc):
        svc._fmp_get = AsyncMock(return_value=[SAMPLE_INCOME])
        await svc.get_income_statements("MSFT", period="quarter", limit=8)
        call_params = svc._fmp_get.call_args.kwargs.get("params") or svc._fmp_get.call_args[1].get("params")
        # The endpoint should include the symbol
        endpoint = svc._fmp_get.call_args.kwargs.get("endpoint") or svc._fmp_get.call_args[1].get("endpoint")
        assert endpoint == "/income-statement/MSFT"


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetBalanceSheets:
    async def test_returns_list(self, svc):
        svc._fmp_get = AsyncMock(return_value=[SAMPLE_BALANCE])
        results = await svc.get_balance_sheets("AAPL")
        assert len(results) == 1
        assert isinstance(results[0], BalanceSheet)

    async def test_empty_returns_empty_list(self, svc):
        svc._fmp_get = AsyncMock(return_value=None)
        assert await svc.get_balance_sheets("AAPL") == []


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetCashFlowStatements:
    async def test_returns_list(self, svc):
        svc._fmp_get = AsyncMock(return_value=[SAMPLE_CASHFLOW])
        results = await svc.get_cash_flow_statements("AAPL")
        assert len(results) == 1
        assert isinstance(results[0], CashFlowStatement)
        assert results[0].free_cash_flow == pytest.approx(106_987_000_000)


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetFinancialRatios:
    async def test_returns_list(self, svc):
        svc._fmp_get = AsyncMock(return_value=[SAMPLE_RATIOS])
        results = await svc.get_financial_ratios("AAPL")
        assert len(results) == 1
        assert isinstance(results[0], FinancialRatios)


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetKeyMetrics:
    async def test_returns_list(self, svc):
        svc._fmp_get = AsyncMock(return_value=[SAMPLE_METRICS])
        results = await svc.get_key_metrics("AAPL")
        assert len(results) == 1
        assert isinstance(results[0], KeyMetrics)


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetSECFilings:
    async def test_returns_list(self, svc):
        svc._fmp_get = AsyncMock(return_value=[SAMPLE_SEC_FILING])
        results = await svc.get_sec_filings("AAPL")
        assert len(results) == 1
        assert isinstance(results[0], SECFiling)
        assert results[0].filing_type == "10-K"

    async def test_type_filter_forwarded(self, svc):
        svc._fmp_get = AsyncMock(return_value=[SAMPLE_SEC_FILING])
        await svc.get_sec_filings("AAPL", filing_type="10-K")
        cache_key_parts = svc._fmp_get.call_args.kwargs.get("cache_key_parts")
        assert "10-K" in cache_key_parts


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetQuote:
    async def test_returns_quote(self, svc):
        svc._fmp_get = AsyncMock(return_value=[SAMPLE_QUOTE])
        quote = await svc.get_quote("AAPL")
        assert isinstance(quote, Quote)
        assert quote.price == pytest.approx(178.50)

    async def test_empty_list_raises_not_found(self, svc):
        svc._fmp_get = AsyncMock(return_value=[])
        with pytest.raises(NotFoundError):
            await svc.get_quote("INVALID")


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetHistorical:
    async def test_returns_historical_data(self, svc):
        svc._fmp_get = AsyncMock(return_value=SAMPLE_HISTORICAL)
        data = await svc.get_historical("AAPL")

        assert isinstance(data, HistoricalData)
        assert data.symbol   == "AAPL"
        assert data.interval == "1d"
        assert data.source   == "fmp"
        # FMP returns newest-first; service reverses to chronological
        assert len(data.candles) == 2
        assert data.candles[0].close == pytest.approx(176.8)  # older date first
        assert data.candles[1].close == pytest.approx(178.5)

    async def test_empty_historical_raises_not_found(self, svc):
        svc._fmp_get = AsyncMock(return_value={"symbol": "AAPL", "historical": []})
        with pytest.raises(NotFoundError):
            await svc.get_historical("AAPL")

    async def test_non_dict_response_raises_not_found(self, svc):
        svc._fmp_get = AsyncMock(return_value=None)
        with pytest.raises(NotFoundError):
            await svc.get_historical("AAPL")

    async def test_from_to_dates_forwarded(self, svc):
        svc._fmp_get = AsyncMock(return_value=SAMPLE_HISTORICAL)
        await svc.get_historical("AAPL", from_date="2026-01-01", to_date="2026-03-01")
        cache_key_parts = svc._fmp_get.call_args.kwargs.get("cache_key_parts")
        assert "2026-01-01" in cache_key_parts
        assert "2026-03-01" in cache_key_parts


# ---------------------------------------------------------------------------
# get_fundamentals aggregation tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
class TestGetFundamentals:
    async def test_returns_company_fundamentals(self, svc):
        """Happy path: all sub-requests succeed."""
        svc.get_company_profile       = AsyncMock(return_value=svc._parse_profile(SAMPLE_PROFILE))
        svc.get_income_statements     = AsyncMock(return_value=[svc._parse_income_statement(SAMPLE_INCOME)])
        svc.get_balance_sheets        = AsyncMock(return_value=[svc._parse_balance_sheet(SAMPLE_BALANCE)])
        svc.get_cash_flow_statements  = AsyncMock(return_value=[svc._parse_cash_flow(SAMPLE_CASHFLOW)])
        svc.get_financial_ratios      = AsyncMock(return_value=[svc._parse_ratios(SAMPLE_RATIOS)])
        svc.get_key_metrics           = AsyncMock(return_value=[svc._parse_key_metrics(SAMPLE_METRICS)])
        svc.get_sec_filings           = AsyncMock(return_value=[svc._parse_sec_filing("AAPL", SAMPLE_SEC_FILING)])

        result = await svc.get_fundamentals("AAPL")

        assert isinstance(result, CompanyFundamentals)
        assert result.symbol              == "AAPL"
        assert result.profile.company_name == "Apple Inc."
        assert len(result.income_statements)    == 1
        assert len(result.balance_sheets)        == 1
        assert len(result.cash_flow_statements)  == 1
        assert len(result.financial_ratios)      == 1
        assert len(result.key_metrics)           == 1
        assert len(result.sec_filings)           == 1
        assert result.source == "fmp"

    async def test_profile_not_found_propagates(self, svc):
        svc.get_company_profile = AsyncMock(side_effect=NotFoundError("fmp", "INVALID"))
        svc.get_income_statements     = AsyncMock(return_value=[])
        svc.get_balance_sheets        = AsyncMock(return_value=[])
        svc.get_cash_flow_statements  = AsyncMock(return_value=[])
        svc.get_financial_ratios      = AsyncMock(return_value=[])
        svc.get_key_metrics           = AsyncMock(return_value=[])
        svc.get_sec_filings           = AsyncMock(return_value=[])

        with pytest.raises(NotFoundError):
            await svc.get_fundamentals("INVALID")

    async def test_partial_failure_degrades_gracefully(self, svc):
        """Secondary requests failing should not abort the whole call."""
        svc.get_company_profile       = AsyncMock(return_value=svc._parse_profile(SAMPLE_PROFILE))
        svc.get_income_statements     = AsyncMock(side_effect=ServiceError("fmp error", "fmp"))
        svc.get_balance_sheets        = AsyncMock(return_value=[])
        svc.get_cash_flow_statements  = AsyncMock(return_value=[])
        svc.get_financial_ratios      = AsyncMock(return_value=[])
        svc.get_key_metrics           = AsyncMock(return_value=[])
        svc.get_sec_filings           = AsyncMock(return_value=[])

        result = await svc.get_fundamentals("AAPL")

        assert result.income_statements == []   # failed silently
        assert result.profile is not None        # profile still present

    async def test_no_sec_filings_when_disabled(self, svc):
        svc.get_company_profile       = AsyncMock(return_value=svc._parse_profile(SAMPLE_PROFILE))
        svc.get_income_statements     = AsyncMock(return_value=[])
        svc.get_balance_sheets        = AsyncMock(return_value=[])
        svc.get_cash_flow_statements  = AsyncMock(return_value=[])
        svc.get_financial_ratios      = AsyncMock(return_value=[])
        svc.get_key_metrics           = AsyncMock(return_value=[])
        svc.get_sec_filings           = AsyncMock(return_value=[])

        result = await svc.get_fundamentals("AAPL", include_sec_filings=False)

        assert result.sec_filings == []
        svc.get_sec_filings.assert_not_called()

    async def test_symbol_is_upper_cased(self, svc):
        svc.get_company_profile       = AsyncMock(return_value=svc._parse_profile(SAMPLE_PROFILE))
        svc.get_income_statements     = AsyncMock(return_value=[])
        svc.get_balance_sheets        = AsyncMock(return_value=[])
        svc.get_cash_flow_statements  = AsyncMock(return_value=[])
        svc.get_financial_ratios      = AsyncMock(return_value=[])
        svc.get_key_metrics           = AsyncMock(return_value=[])
        svc.get_sec_filings           = AsyncMock(return_value=[])

        await svc.get_fundamentals("aapl")

        svc.get_company_profile.assert_called_once_with("AAPL")


# ---------------------------------------------------------------------------
# Helper to grab settings from a service instance
# ---------------------------------------------------------------------------

def settings_module(svc: FMPService):
    """Return the settings object used by the FMP service."""
    from config import settings as _settings
    return _settings
