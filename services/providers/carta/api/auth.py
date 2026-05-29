from pydantic import BaseModel
from typing import Dict, Optional
from datetime import datetime

class CartaAuthContext(BaseModel):
    session_id: str
    extracted_at: datetime
    last_refreshed_at: datetime
    version: int
    cookies: Dict[str, str]
    csrf_token: str
    user_agent: str
    account_id: Optional[str] = None


class CartaRuntimeContext(BaseModel):
    login_base_url: str
    app_base_url: str
    api_base_url: str
    firm_id: Optional[int] = None
    persona: Optional[str] = None
    csrf_token: str
    current_route: Optional[str] = None


class CartaUIRoutes:
    """Helper for generating strictly bounded runtime navigation routes."""
    
    @staticmethod
    def dashboard(firm_id: int) -> str:
        return f"/investors/firm/{firm_id}/portfolio/gp-activity/"
        
    @staticmethod
    def investments(firm_id: int) -> str:
        return f"/investors/firm/{firm_id}/portfolio/investments/"
        
    @staticmethod
    def tasks(firm_id: int) -> str:
        return f"/investors/firm/{firm_id}/portfolio/gp-activity/tasks/"



