from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
import json

from .canonical_entities import (
    Organization, Fund, PortfolioCompany, Investor, Holding,
    Security, Valuation, Transaction, Document, Person
)

@dataclass
class CompanyAggregate:
    """Convenience structure grouping all entities related to a single portfolio company."""
    company: PortfolioCompany
    holdings: List[Holding] = field(default_factory=list)
    securities: List[Security] = field(default_factory=list)
    valuations: List[Valuation] = field(default_factory=list)
    transactions: List[Transaction] = field(default_factory=list)
    documents: List[Document] = field(default_factory=list)
    people: List[Person] = field(default_factory=list)

class CanonicalEntityStore:
    """An indexed registry of all canonical entities."""
    
    def __init__(self):
        # Registries (dict keyed by entity.id)
        self.organizations: Dict[str, Organization] = {}
        self.funds: Dict[str, Fund] = {}
        self.companies: Dict[str, PortfolioCompany] = {}
        self.investors: Dict[str, Investor] = {}
        self.holdings: Dict[str, Holding] = {}
        self.securities: Dict[str, Security] = {}
        self.valuations: Dict[str, Valuation] = {}
        self.transactions: Dict[str, Transaction] = {}
        self.documents: Dict[str, Document] = {}
        self.people: Dict[str, Person] = {}

        # Indexes for fast lookup
        self._ext_id_index: Dict[Tuple[str, str, str], str] = {}  # (provider, entity_type, ext_id) -> canonical_id
        
        # We also want to map external ID back to the canonical ID,
        # but some entities might not have a clean external ID so we index by ID directly.
        # Let's keep it simple.

    def _index_entity(self, entity):
        provider = getattr(entity, 'source_provider', '')
        ext_id = getattr(entity, 'external_id', getattr(entity, 'id', ''))
        entity_type = type(entity).__name__
        self._ext_id_index[(provider, entity_type, ext_id)] = entity.id

    def register(self, entity) -> str:
        """Register a single entity into the store."""
        etype = type(entity).__name__
        if etype == 'Organization':
            self.organizations[entity.id] = entity
        elif etype == 'Fund':
            self.funds[entity.id] = entity
        elif etype == 'PortfolioCompany':
            self.companies[entity.id] = entity
        elif etype == 'Investor':
            self.investors[entity.id] = entity
        elif etype == 'Holding':
            self.holdings[entity.id] = entity
        elif etype == 'Security':
            self.securities[entity.id] = entity
        elif etype == 'Valuation':
            self.valuations[entity.id] = entity
        elif etype == 'Transaction':
            self.transactions[entity.id] = entity
        elif etype == 'Document':
            self.documents[entity.id] = entity
        elif etype == 'Person':
            self.people[entity.id] = entity
        else:
            raise ValueError(f"Unknown entity type: {etype}")
            
        self._index_entity(entity)
        return entity.id

    def register_batch(self, entities: List) -> List[str]:
        """Register multiple entities."""
        return [self.register(e) for e in entities]

    def get_company_aggregate(self, company_id: str) -> CompanyAggregate:
        """Get a CompanyAggregate for a given canonical company_id."""
        if company_id not in self.companies:
            raise KeyError(f"Company {company_id} not found")
            
        company = self.companies[company_id]
        agg = CompanyAggregate(company=company)
        
        # Populate related lists
        agg.holdings = [h for h in self.holdings.values() if h.company_id == company_id]
        agg.securities = [s for s in self.securities.values() if s.company_id == company_id]
        agg.valuations = [v for v in self.valuations.values() if v.company_id == company_id]
        agg.transactions = [t for t in self.transactions.values() if t.company_id == company_id]
        agg.documents = [d for d in self.documents.values() if d.entity_id == company_id and d.entity_type == 'PortfolioCompany']
        agg.people = [p for p in self.people.values() if p.company_id == company_id]
        
        return agg

    def list_companies(self) -> List[PortfolioCompany]:
        return list(self.companies.values())

    def get_transactions_for(self, company_id: str) -> List[Transaction]:
        return [t for t in self.transactions.values() if t.company_id == company_id]

    def get_securities_for(self, company_id: str) -> List[Security]:
        return [s for s in self.securities.values() if s.company_id == company_id]

    def get_valuations_for(self, company_id: str) -> List[Valuation]:
        return [v for v in self.valuations.values() if v.company_id == company_id]

    def get_people_for(self, company_id: str) -> List[Person]:
        return [p for p in self.people.values() if p.company_id == company_id]

    def get_holdings_for(self, company_id: str) -> List[Holding]:
        return [h for h in self.holdings.values() if h.company_id == company_id]

    def get_organization(self) -> Optional[Organization]:
        if not self.organizations:
            return None
        return list(self.organizations.values())[0]

    def list_funds(self) -> List[Fund]:
        return list(self.funds.values())

    def list_investors(self) -> List[Investor]:
        return list(self.investors.values())
        
    def get_fund_by_name(self, name: str) -> Optional[Fund]:
        for f in self.funds.values():
            if f.name == name:
                return f
        return None
