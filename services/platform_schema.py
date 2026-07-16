from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum

class PlatformBaseModel(BaseModel):
    """Base model for all platform schema entities."""
    pass

class InvInvestment(PlatformBaseModel):
    asset_id: str
    asset_name: str
    investment_amount: Optional[float] = None
    valuation: Optional[float] = None
    irr: Optional[float] = None
    investment_date: Optional[str] = None
    ownership_percentage: Optional[float] = None
    asset_category: str = "Venture"
    
    # N/A for venture (Physical assets)
    vin: Optional[str] = None
    tail_id: Optional[str] = None
    carat_weight: Optional[float] = None
    movement_type: Optional[str] = None

class InvAssetExtraInfo(PlatformBaseModel):
    investment_id: str
    industry_overview: Optional[str] = None
    investment_thesis: Optional[str] = None
    industry_tailwinds: Optional[str] = None
    customer_segment: Optional[str] = None
    financials: Optional[str] = None

class InvAssetTeam(PlatformBaseModel):
    investment_id: str
    first_name: str
    last_name: str
    email: Optional[str] = None
    designation: Optional[str] = None

class InvAssetValuation(PlatformBaseModel):
    investment_id: str
    amount: float
    year: str
    date: Optional[str] = None

class InvCapCall(PlatformBaseModel):
    investment_id: str
    amount: float
    notes: Optional[str] = None
    date: str
    fund_name: Optional[str] = None

class InvestmentLog(PlatformBaseModel):
    investment_id: str
    investment_amount: float
    market_value: Optional[float] = None
    investment_date: str

class InvInvestmentTransaction(PlatformBaseModel):
    investment_id: str
    amount: float
    name: str
    tr_date: Optional[str] = None
    tr_type: Optional[str] = None
    tr_direction: Optional[str] = None

class InvInvestmentFirm(PlatformBaseModel):
    investment_id: str
    company_name: str
    fund_count: Optional[int] = None
    aum_value: Optional[float] = None

class InvInvestmentFocus(PlatformBaseModel):
    investment_id: str
    name: str
    cost: Optional[float] = None
    current_year_valuation: Optional[float] = None
    moic: Optional[float] = None

class InvInvestmentSector(PlatformBaseModel):
    investment_id: str
    name: str
    stage_name: Optional[str] = None

class InvInvestmentCertificate(PlatformBaseModel):
    investment_id: str
    cert_number: Optional[str] = None
    issue_date: Optional[str] = None
    cert_status: Optional[str] = None

class InvInvestmentDistributionHistory(PlatformBaseModel):
    investment_id: str
    total_amount: float
    lp_name: Optional[str] = None

class InvLiquidityDistribution(PlatformBaseModel):
    investment_id: str
    amount: float
    source: Optional[str] = None

class InvInvestmentExpense(PlatformBaseModel):
    investment_id: str
    expense_category: str
    vendor: Optional[str] = None
    cost: float
    expense_date: str

class InvInvestmentInterest(PlatformBaseModel):
    investment_id: str
    month_year: str
    interest_earned: float

class InvInvestmentService(PlatformBaseModel):
    investment_id: str
    service_type: str
    cost: float
    service_date: str

class InvAssetUsageLog(PlatformBaseModel):
    investment_id: str
    usage_date: str
    usage_hours: float

class ExtraInfoRecentDevelopment(PlatformBaseModel):
    investment_id: str
    description: str
    development_date: str

class ResearchGrowingTraction(PlatformBaseModel):
    investment_id: str
    description: str

class PartnerCapitalAccountSummary(PlatformBaseModel):
    investment_id: str
    partner_id: str
    fund_uuid: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    beginning_balance: Optional[float] = None
    contributions: Optional[float] = None
    distributions: Optional[float] = None
    net_income: Optional[float] = None
    ending_balance: Optional[float] = None
    currency: Optional[str] = "USD"

