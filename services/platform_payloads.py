from typing import Optional
from pydantic import BaseModel

class PortfolioInvestmentUpdateData(BaseModel):
    valuation: Optional[float] = None
    valuation_year: Optional[str] = None

class PortfolioInvestmentUpdatePayload(BaseModel):
    org_id: str
    user_id: str
    investment_id: str
    data: PortfolioInvestmentUpdateData
