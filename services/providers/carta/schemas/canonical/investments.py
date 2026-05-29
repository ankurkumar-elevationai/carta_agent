from pydantic import BaseModel
from decimal import Decimal
from typing import Optional

class CanonicalInvestment(BaseModel):
    """
    Canonical representation of a Carta Investment.
    This abstraction insulates downstream agents and workflows
    from upstream Carta schema drift.
    """
    investment_id: str
    company_name: str
    holding_type: Optional[str] = None
    valuation: Optional[Decimal] = None
    ownership_percent: Optional[Decimal] = None
    
    # Additional fields can be mapped here as discovered
    shares_held: Optional[Decimal] = None
    as_of_date: Optional[str] = None
