"""
Fundamental data models for company financials, ratios, and SEC filings.
Used primarily by the FMP (Financial Modeling Prep) service.
"""
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class CompanyProfile(BaseModel):
    """Company profile and basic information."""

    symbol: str = Field(..., description="Ticker symbol")
    company_name: str = Field(..., description="Full company name")
    exchange: str = Field(..., description="Stock exchange (NYSE, NASDAQ, etc.)")
    sector: Optional[str] = Field(None, description="Industry sector")
    industry: Optional[str] = Field(None, description="Industry sub-sector")
    description: Optional[str] = Field(None, description="Company business description")
    ceo: Optional[str] = Field(None, description="Chief Executive Officer")
    website: Optional[str] = Field(None, description="Company website URL")
    country: Optional[str] = Field(None, description="Country of incorporation")
    employees: Optional[int] = Field(None, description="Number of full-time employees")
    currency: str = Field(default="USD", description="Reporting currency")
    market_cap: Optional[float] = Field(None, description="Market capitalization")
    beta: Optional[float] = Field(None, description="Beta coefficient (market risk)")
    price: Optional[float] = Field(None, description="Current stock price")
    avg_volume: Optional[float] = Field(None, description="Average trading volume")
    ipo_date: Optional[str] = Field(None, description="IPO date (YYYY-MM-DD)")
    image: Optional[str] = Field(None, description="Company logo URL")
    is_etf: bool = Field(default=False, description="Whether this is an ETF")
    is_actively_trading: bool = Field(default=True, description="Whether actively trading")
    source: str = Field(default="fmp", description="Data source")

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "AAPL",
                "company_name": "Apple Inc.",
                "exchange": "NASDAQ",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "description": "Apple Inc. designs, manufactures...",
                "ceo": "Tim Cook",
                "website": "https://www.apple.com",
                "country": "US",
                "employees": 164000,
                "currency": "USD",
                "market_cap": 2800000000000.0,
                "beta": 1.25,
                "price": 178.50,
                "avg_volume": 55000000,
                "ipo_date": "1980-12-12",
                "is_etf": False,
                "is_actively_trading": True,
                "source": "fmp",
            }
        }


class IncomeStatement(BaseModel):
    """Annual or quarterly income statement data."""

    symbol: str = Field(..., description="Ticker symbol")
    date: str = Field(..., description="Reporting period end date (YYYY-MM-DD)")
    period: str = Field(..., description="Period type: annual or quarter")
    calendar_year: Optional[str] = Field(None, description="Calendar year")
    currency: str = Field(default="USD", description="Reporting currency")

    # Revenue
    revenue: Optional[float] = Field(None, description="Total revenue")
    cost_of_revenue: Optional[float] = Field(None, description="Cost of goods sold")
    gross_profit: Optional[float] = Field(None, description="Gross profit")
    gross_profit_ratio: Optional[float] = Field(None, description="Gross profit margin")

    # Operating expenses
    research_and_development_expenses: Optional[float] = Field(
        None, description="R&D expenses"
    )
    selling_general_and_administrative_expenses: Optional[float] = Field(
        None, description="SG&A expenses"
    )
    operating_expenses: Optional[float] = Field(None, description="Total operating expenses")
    operating_income: Optional[float] = Field(None, description="Operating income (EBIT)")
    operating_income_ratio: Optional[float] = Field(None, description="Operating margin")

    # Below the line
    interest_expense: Optional[float] = Field(None, description="Interest expense")
    income_before_tax: Optional[float] = Field(None, description="Pre-tax income")
    income_tax_expense: Optional[float] = Field(None, description="Income tax expense")
    net_income: Optional[float] = Field(None, description="Net income")
    net_income_ratio: Optional[float] = Field(None, description="Net profit margin")

    # Per share
    eps: Optional[float] = Field(None, description="Basic earnings per share")
    eps_diluted: Optional[float] = Field(None, description="Diluted earnings per share")
    weighted_average_shares: Optional[float] = Field(
        None, description="Weighted average shares outstanding (basic)"
    )
    weighted_average_shares_diluted: Optional[float] = Field(
        None, description="Weighted average shares outstanding (diluted)"
    )

    # EBITDA
    ebitda: Optional[float] = Field(None, description="EBITDA")
    depreciation_and_amortization: Optional[float] = Field(
        None, description="D&A expenses"
    )

    source: str = Field(default="fmp", description="Data source")

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "AAPL",
                "date": "2025-09-28",
                "period": "annual",
                "calendar_year": "2025",
                "currency": "USD",
                "revenue": 391035000000,
                "gross_profit": 170782000000,
                "gross_profit_ratio": 0.437,
                "operating_income": 113000000000,
                "net_income": 94000000000,
                "net_income_ratio": 0.240,
                "eps": 6.09,
                "eps_diluted": 6.08,
                "source": "fmp",
            }
        }


class BalanceSheet(BaseModel):
    """Annual or quarterly balance sheet data."""

    symbol: str = Field(..., description="Ticker symbol")
    date: str = Field(..., description="Reporting period end date (YYYY-MM-DD)")
    period: str = Field(..., description="Period type: annual or quarter")
    calendar_year: Optional[str] = Field(None, description="Calendar year")
    currency: str = Field(default="USD", description="Reporting currency")

    # Current assets
    cash_and_equivalents: Optional[float] = Field(
        None, description="Cash and cash equivalents"
    )
    short_term_investments: Optional[float] = Field(None, description="Short-term investments")
    net_receivables: Optional[float] = Field(None, description="Net accounts receivable")
    inventory: Optional[float] = Field(None, description="Inventory")
    total_current_assets: Optional[float] = Field(None, description="Total current assets")

    # Non-current assets
    property_plant_equipment_net: Optional[float] = Field(
        None, description="PP&E net of depreciation"
    )
    goodwill: Optional[float] = Field(None, description="Goodwill")
    intangible_assets: Optional[float] = Field(None, description="Intangible assets")
    total_non_current_assets: Optional[float] = Field(
        None, description="Total non-current assets"
    )
    total_assets: Optional[float] = Field(None, description="Total assets")

    # Current liabilities
    accounts_payable: Optional[float] = Field(None, description="Accounts payable")
    short_term_debt: Optional[float] = Field(None, description="Short-term debt")
    total_current_liabilities: Optional[float] = Field(
        None, description="Total current liabilities"
    )

    # Non-current liabilities
    long_term_debt: Optional[float] = Field(None, description="Long-term debt")
    total_non_current_liabilities: Optional[float] = Field(
        None, description="Total non-current liabilities"
    )
    total_liabilities: Optional[float] = Field(None, description="Total liabilities")

    # Equity
    retained_earnings: Optional[float] = Field(None, description="Retained earnings")
    total_stockholders_equity: Optional[float] = Field(
        None, description="Total shareholders' equity"
    )
    total_liabilities_and_equity: Optional[float] = Field(
        None, description="Total liabilities and equity"
    )

    # Derived
    total_debt: Optional[float] = Field(None, description="Total debt (short + long term)")
    net_debt: Optional[float] = Field(None, description="Net debt (debt minus cash)")

    source: str = Field(default="fmp", description="Data source")


class CashFlowStatement(BaseModel):
    """Annual or quarterly cash flow statement data."""

    symbol: str = Field(..., description="Ticker symbol")
    date: str = Field(..., description="Reporting period end date (YYYY-MM-DD)")
    period: str = Field(..., description="Period type: annual or quarter")
    calendar_year: Optional[str] = Field(None, description="Calendar year")
    currency: str = Field(default="USD", description="Reporting currency")

    # Operating activities
    net_income: Optional[float] = Field(None, description="Net income")
    depreciation_and_amortization: Optional[float] = Field(None, description="D&A")
    stock_based_compensation: Optional[float] = Field(
        None, description="Stock-based compensation"
    )
    change_in_working_capital: Optional[float] = Field(
        None, description="Change in working capital"
    )
    operating_cash_flow: Optional[float] = Field(
        None, description="Net cash from operating activities"
    )

    # Investing activities
    capital_expenditure: Optional[float] = Field(
        None, description="Capital expenditures (negative = outflow)"
    )
    acquisitions: Optional[float] = Field(None, description="Acquisitions net of disposals")
    purchases_of_investments: Optional[float] = Field(
        None, description="Purchases of investments"
    )
    sales_of_investments: Optional[float] = Field(None, description="Sales of investments")
    investing_cash_flow: Optional[float] = Field(
        None, description="Net cash from investing activities"
    )

    # Financing activities
    debt_repayment: Optional[float] = Field(None, description="Debt repayment")
    common_stock_issued: Optional[float] = Field(None, description="Common stock issued")
    common_stock_repurchased: Optional[float] = Field(
        None, description="Common stock repurchased (buybacks)"
    )
    dividends_paid: Optional[float] = Field(None, description="Dividends paid")
    financing_cash_flow: Optional[float] = Field(
        None, description="Net cash from financing activities"
    )

    # Summary
    net_change_in_cash: Optional[float] = Field(
        None, description="Net change in cash and equivalents"
    )
    free_cash_flow: Optional[float] = Field(
        None, description="Free cash flow (operating - capex)"
    )

    source: str = Field(default="fmp", description="Data source")


class FinancialRatios(BaseModel):
    """Key financial ratios for valuation and analysis."""

    symbol: str = Field(..., description="Ticker symbol")
    date: str = Field(..., description="Reporting period end date (YYYY-MM-DD)")
    period: str = Field(..., description="Period type: annual or quarter")
    calendar_year: Optional[str] = Field(None, description="Calendar year")

    # Liquidity ratios
    current_ratio: Optional[float] = Field(
        None, description="Current assets / Current liabilities"
    )
    quick_ratio: Optional[float] = Field(
        None, description="(Current assets - Inventory) / Current liabilities"
    )
    cash_ratio: Optional[float] = Field(
        None, description="Cash / Current liabilities"
    )

    # Profitability ratios
    gross_profit_margin: Optional[float] = Field(None, description="Gross profit / Revenue")
    operating_profit_margin: Optional[float] = Field(
        None, description="Operating income / Revenue"
    )
    net_profit_margin: Optional[float] = Field(None, description="Net income / Revenue")
    return_on_equity: Optional[float] = Field(
        None, description="Net income / Shareholders' equity"
    )
    return_on_assets: Optional[float] = Field(None, description="Net income / Total assets")
    return_on_capital_employed: Optional[float] = Field(
        None, description="EBIT / Capital employed"
    )

    # Valuation ratios
    price_earnings_ratio: Optional[float] = Field(None, description="P/E ratio")
    price_to_book_ratio: Optional[float] = Field(None, description="P/B ratio")
    price_to_sales_ratio: Optional[float] = Field(None, description="P/S ratio")
    price_to_free_cash_flow: Optional[float] = Field(None, description="P/FCF ratio")
    ev_to_ebitda: Optional[float] = Field(None, description="EV/EBITDA ratio")

    # Leverage ratios
    debt_equity_ratio: Optional[float] = Field(None, description="Total debt / Equity")
    debt_ratio: Optional[float] = Field(None, description="Total debt / Total assets")
    interest_coverage: Optional[float] = Field(
        None, description="EBIT / Interest expense"
    )

    # Efficiency ratios
    asset_turnover: Optional[float] = Field(None, description="Revenue / Total assets")
    inventory_turnover: Optional[float] = Field(
        None, description="COGS / Average inventory"
    )
    days_sales_outstanding: Optional[float] = Field(
        None, description="Accounts receivable / (Revenue / 365)"
    )

    # Per-share metrics
    dividend_yield: Optional[float] = Field(None, description="Annual dividend / Price")
    payout_ratio: Optional[float] = Field(None, description="Dividends / Net income")
    earnings_yield: Optional[float] = Field(None, description="EPS / Price (inverse P/E)")
    free_cash_flow_yield: Optional[float] = Field(
        None, description="FCF per share / Price"
    )

    source: str = Field(default="fmp", description="Data source")


class KeyMetrics(BaseModel):
    """Key financial metrics combining income statement, balance sheet and market data."""

    symbol: str = Field(..., description="Ticker symbol")
    date: str = Field(..., description="Reporting period end date (YYYY-MM-DD)")
    period: str = Field(..., description="Period type: annual or quarter")
    calendar_year: Optional[str] = Field(None, description="Calendar year")
    currency: str = Field(default="USD", description="Reporting currency")

    # Per share
    revenue_per_share: Optional[float] = Field(None, description="Revenue per share")
    net_income_per_share: Optional[float] = Field(None, description="EPS")
    operating_cash_flow_per_share: Optional[float] = Field(
        None, description="Operating cash flow per share"
    )
    free_cash_flow_per_share: Optional[float] = Field(
        None, description="FCF per share"
    )
    cash_per_share: Optional[float] = Field(None, description="Cash and equivalents per share")
    book_value_per_share: Optional[float] = Field(None, description="Book value per share")

    # Enterprise value based
    enterprise_value: Optional[float] = Field(None, description="Enterprise value")
    ev_to_sales: Optional[float] = Field(None, description="EV / Revenue")
    ev_to_ebitda: Optional[float] = Field(None, description="EV / EBITDA")
    ev_to_operating_cash_flow: Optional[float] = Field(
        None, description="EV / Operating cash flow"
    )
    ev_to_free_cash_flow: Optional[float] = Field(None, description="EV / FCF")

    # Price multiples
    pe_ratio: Optional[float] = Field(None, description="Price / EPS")
    pb_ratio: Optional[float] = Field(None, description="Price / Book value")
    ps_ratio: Optional[float] = Field(None, description="Price / Sales per share")
    price_to_free_cash_flow: Optional[float] = Field(None, description="Price / FCF per share")

    # Leverage
    debt_to_equity: Optional[float] = Field(None, description="Total debt / Equity")
    debt_to_assets: Optional[float] = Field(None, description="Total debt / Assets")
    net_debt_to_ebitda: Optional[float] = Field(None, description="Net debt / EBITDA")

    # Returns
    roe: Optional[float] = Field(None, description="Return on equity")
    roa: Optional[float] = Field(None, description="Return on assets")
    roic: Optional[float] = Field(None, description="Return on invested capital")

    # Dividend
    dividend_yield: Optional[float] = Field(None, description="Trailing dividend yield")
    dividend_per_share: Optional[float] = Field(None, description="Annual dividend per share")
    payout_ratio: Optional[float] = Field(None, description="Dividend payout ratio")

    source: str = Field(default="fmp", description="Data source")


class SECFiling(BaseModel):
    """SEC filing metadata from EDGAR."""

    symbol: str = Field(..., description="Ticker symbol")
    cik: Optional[str] = Field(None, description="CIK number")
    filing_type: str = Field(..., description="Filing type (10-K, 10-Q, 8-K, etc.)")
    accepted_date: Optional[str] = Field(
        None, description="Date filing was accepted by SEC (YYYY-MM-DD HH:MM:SS)"
    )
    filing_date: Optional[str] = Field(None, description="Filing date (YYYY-MM-DD)")
    link: Optional[str] = Field(None, description="Link to filing index page")
    final_link: Optional[str] = Field(None, description="Direct link to primary document")
    source: str = Field(default="fmp", description="Data source")

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "AAPL",
                "cik": "0000320193",
                "filing_type": "10-K",
                "accepted_date": "2025-11-01 06:01:05",
                "filing_date": "2025-11-01",
                "link": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=AAPL&type=10-K",
                "final_link": "https://www.sec.gov/Archives/edgar/data/320193/...",
                "source": "fmp",
            }
        }


class CompanyFundamentals(BaseModel):
    """
    Aggregated fundamentals for a company.

    Combines profile, latest financial statements, ratios, and metrics
    into a single response object.
    """

    symbol: str = Field(..., description="Ticker symbol")
    profile: Optional[CompanyProfile] = Field(None, description="Company profile")
    income_statements: List[IncomeStatement] = Field(
        default_factory=list,
        description="Historical income statements (most recent first)",
    )
    balance_sheets: List[BalanceSheet] = Field(
        default_factory=list,
        description="Historical balance sheets (most recent first)",
    )
    cash_flow_statements: List[CashFlowStatement] = Field(
        default_factory=list,
        description="Historical cash flow statements (most recent first)",
    )
    financial_ratios: List[FinancialRatios] = Field(
        default_factory=list,
        description="Historical financial ratios (most recent first)",
    )
    key_metrics: List[KeyMetrics] = Field(
        default_factory=list,
        description="Historical key metrics (most recent first)",
    )
    sec_filings: List[SECFiling] = Field(
        default_factory=list,
        description="Recent SEC filings (most recent first)",
    )
    source: str = Field(default="fmp", description="Data source")
    fetched_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when data was fetched",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "AAPL",
                "profile": {"symbol": "AAPL", "company_name": "Apple Inc."},
                "income_statements": [],
                "balance_sheets": [],
                "cash_flow_statements": [],
                "financial_ratios": [],
                "key_metrics": [],
                "sec_filings": [],
                "source": "fmp",
            }
        }
