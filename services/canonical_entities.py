import uuid
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

# Stable namespace for deterministic UUID5 generation
NAMESPACE_CANONICAL = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

def generate_canonical_id(provider: str, entity_type: str, external_id: str) -> str:
    """Generate a deterministic UUID based on provider, entity type, and external ID."""
    return str(uuid.uuid5(NAMESPACE_CANONICAL, f"{provider}:{entity_type}:{external_id}"))

@dataclass
class Organization:
    id: str
    external_id: str
    name: str
    admin_name: Optional[str] = None
    admin_email: Optional[str] = None
    admin_title: Optional[str] = None
    source_provider: str = ""
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Fund:
    id: str
    external_id: str
    organization_id: str
    name: str
    fund_type: str
    currency: Optional[str] = None
    source_provider: str = ""
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class PortfolioCompany:
    id: str
    external_id: str
    name: str
    legal_name: Optional[str] = None
    dba: Optional[str] = None
    industry: Optional[str] = None
    date_of_incorporation: Optional[str] = None
    address: Optional[str] = None
    ceo: Optional[str] = None
    website: Optional[str] = None
    description: Optional[str] = None
    source_provider: str = ""
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Investor:
    id: str
    external_id: str
    name: str
    total_ownership_pct: Optional[float] = None
    source_provider: str = ""
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Holding:
    id: str
    fund_id: str
    company_id: str
    held_since: Optional[str] = None
    cash_cost: Optional[float] = None
    ownership_pct: Optional[float] = None
    currency: Optional[str] = None
    irr_percentage: Optional[float] = None
    multiple: Optional[float] = None
    source_provider: str = ""

@dataclass
class Security:
    id: str
    external_id: str
    company_id: str
    owner_id: Optional[str] = None
    label: Optional[str] = None
    issue_date: Optional[str] = None
    issuable_type: Optional[str] = None
    stock_type: Optional[str] = None
    status: Optional[str] = None
    quantity: Optional[float] = None
    cost: Optional[float] = None
    value: Optional[float] = None
    currency: Optional[str] = None
    has_vesting: bool = False
    source_provider: str = ""

@dataclass
class Valuation:
    id: str
    company_id: str
    valuation_date: Optional[str] = None
    post_money: Optional[float] = None
    funds_raised: Optional[float] = None
    share_class: Optional[str] = None
    currency: Optional[str] = None
    source_provider: str = ""

@dataclass
class Transaction:
    id: str
    company_id: str
    description: str
    date: Optional[str] = None
    credit: Optional[float] = None
    debit: Optional[float] = None
    deal_display_names: Optional[str] = None
    source_provider: str = ""

@dataclass
class Document:
    id: str
    entity_id: str
    entity_type: str
    title: str
    document_url: Optional[str] = None
    document_type: Optional[str] = None
    source_provider: str = ""

@dataclass
class Person:
    id: str
    company_id: Optional[str]
    name: str
    email: Optional[str] = None
    title: Optional[str] = None
    is_primary: bool = False
    source_provider: str = ""
