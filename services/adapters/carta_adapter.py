import uuid
import logging
from typing import Dict, Any, List, Optional
from ..canonical_entities import (
    generate_canonical_id, Organization, Fund, PortfolioCompany, Investor,
    Holding, Security, Valuation, Transaction, Document, Person
)
from ..canonical_store import CanonicalEntityStore

log = logging.getLogger(__name__)

class CartaAdapter:
    """Normalizes Carta's raw JSON responses into the provider-agnostic CanonicalEntityStore."""
    
    PROVIDER_NAME = "carta"

    def __init__(self, raw_data: Dict[str, Any]):
        """Initialize with data loaded from business_data.json"""
        self.raw = raw_data
        
    def _cid(self, entity_type: str, ext_id: str) -> str:
        return generate_canonical_id(self.PROVIDER_NAME, entity_type, str(ext_id))
        
    def populate(self, store: CanonicalEntityStore):
        """Map all Carta data into the provided store."""
        
        # 1. Organization
        org_data = self.raw.get("firm", {})
        org_ext_id = org_data.get("firm_uuid") or org_data.get("firm_id", "unknown_org")
        org_id = self._cid("Organization", org_ext_id)
        
        org = Organization(
            id=org_id,
            external_id=str(org_ext_id),
            name=org_data.get("organization_name", org_data.get("name", "Unknown Organization")),
            admin_name=org_data.get("admin"),
            admin_title=org_data.get("title"),
            admin_email=org_data.get("email"),
            source_provider=self.PROVIDER_NAME,
            raw_metadata=org_data
        )
        store.register(org)
        
        # 2. Funds (Funds, SPVs, etc.)
        for fund_data in self.raw.get("funds", []) + self.raw.get("spvs", []):
            f_ext_id = fund_data.get("uuid") or fund_data.get("carta_id")
            if not f_ext_id:
                continue
            
            fund = Fund(
                id=self._cid("Fund", f_ext_id),
                external_id=str(f_ext_id),
                organization_id=org_id,
                name=fund_data.get("name", "Unknown Fund"),
                fund_type=fund_data.get("type", "Fund"),
                source_provider=self.PROVIDER_NAME,
                raw_metadata=fund_data
            )
            store.register(fund)
            
        # We also have fund_structure and fund_relationships, might need cross referencing later

        # 3. Investors
        for inv_data in self.raw.get("investors", []):
            i_ext_id = inv_data.get("uuid", inv_data.get("name", "Unknown Investor"))
            
            investor = Investor(
                id=self._cid("Investor", i_ext_id),
                external_id=str(i_ext_id),
                name=inv_data.get("name", "Unknown Investor"),
                total_ownership_pct=inv_data.get("total_ownership_pct"),
                source_provider=self.PROVIDER_NAME,
                raw_metadata=inv_data
            )
            store.register(investor)
            
        # 4. Investments -> PortfolioCompany, Holding, Valuation, Transaction, Person, Security
        for inv_data in self.raw.get("investments", []):
            c_ext_id = inv_data.get("corporation_id")
            if not c_ext_id:
                continue
                
            c_id = self._cid("PortfolioCompany", c_ext_id)
            profile = inv_data.get("profile", {})
            
            # 4.1 Portfolio Company
            company = PortfolioCompany(
                id=c_id,
                external_id=str(c_ext_id),
                name=inv_data.get("company", "Unknown Company"),
                legal_name=profile.get("legal_name"),
                dba=inv_data.get("dba"),
                industry=profile.get("industry"),
                date_of_incorporation=profile.get("date_of_incorporation"),
                address=profile.get("address"),
                ceo=profile.get("ceo"),
                website=profile.get("website"),
                description=profile.get("description"),
                source_provider=self.PROVIDER_NAME,
                raw_metadata=inv_data
            )
            store.register(company)
            
            # 4.2 Holding (assuming holding belongs to the single Organization for now)
            hs = inv_data.get("holdings_summary", {})
            if hs:
                holding = Holding(
                    id=self._cid("Holding", f"{c_ext_id}_holding"),
                    fund_id="", # Would need to map back to specific fund if known
                    company_id=c_id,
                    held_since=hs.get("held_since"),
                    cash_cost=hs.get("cash_cost"),
                    ownership_pct=hs.get("ownership_pct"),
                    currency=hs.get("currency", "$"),
                    irr_percentage=hs.get("irr_percentage"),
                    multiple=hs.get("multiple"),
                    source_provider=self.PROVIDER_NAME
                )
                store.register(holding)
                
            # 4.3 Valuation (current)
            val_data = inv_data.get("valuation", {})
            if val_data:
                valuation = Valuation(
                    id=self._cid("Valuation", f"{c_ext_id}_current_val"),
                    company_id=c_id,
                    valuation_date=None, # Not provided in top-level valuation
                    post_money=val_data.get("post_money"),
                    funds_raised=val_data.get("funds_raised"),
                    share_class=val_data.get("share_class"),
                    currency=val_data.get("currency", "$"),
                    source_provider=self.PROVIDER_NAME
                )
                store.register(valuation)
                
            # 4.4 Transactions
            irr = inv_data.get("irr", {})
            for idx, tx_data in enumerate(irr.get("transactions", [])):
                tx = Transaction(
                    id=self._cid("Transaction", f"{c_ext_id}_tx_{idx}"),
                    company_id=c_id,
                    description=tx_data.get("description", "Unknown Transaction"),
                    date=tx_data.get("date"),
                    credit=tx_data.get("credit"),
                    debit=tx_data.get("debit"),
                    deal_display_names=tx_data.get("deal_display_names"),
                    source_provider=self.PROVIDER_NAME
                )
                store.register(tx)
                
            # 4.5 People (Contacts)
            for idx, contact in enumerate(inv_data.get("contacts", [])):
                person = Person(
                    id=self._cid("Person", f"{c_ext_id}_contact_{idx}"),
                    company_id=c_id,
                    name=contact.get("name", "Unknown Person"),
                    email=contact.get("email"),
                    title=contact.get("title"),
                    is_primary=contact.get("is_primary", False),
                    source_provider=self.PROVIDER_NAME
                )
                store.register(person)
                
            # 4.6 Securities (Summary & Cap Table)
            for idx, sec in enumerate(inv_data.get("securities", [])):
                s_ext_id = sec.get("name", f"sec_{idx}")
                security = Security(
                    id=self._cid("Security", f"{c_ext_id}_sec_{s_ext_id}"),
                    external_id=s_ext_id,
                    company_id=c_id,
                    label=sec.get("name"),
                    quantity=sec.get("fully_diluted"),
                    status="Summary",
                    source_provider=self.PROVIDER_NAME
                )
                store.register(security)
                
            # 4.7 FMV 409A (Historical Valuations)
            for idx, fmv in enumerate(inv_data.get("fmv_409a", [])):
                val = Valuation(
                    id=self._cid("Valuation", f"{c_ext_id}_fmv_{idx}"),
                    company_id=c_id,
                    valuation_date=fmv.get("effective_date"),
                    post_money=float(fmv.get("price", 0)) if fmv.get("price") else None,
                    share_class="Common (409A)",
                    currency=fmv.get("currency", "$"),
                    source_provider=self.PROVIDER_NAME
                )
                store.register(val)

        # 5. Documents
        for idx, doc_data in enumerate(self.raw.get("documents", [])):
            doc = Document(
                id=self._cid("Document", f"doc_{idx}"),
                entity_id="", # Hard to map at top level without context
                entity_type="Unknown",
                title=doc_data.get("name", "Unknown Document"),
                document_url=doc_data.get("url"),
                document_type=doc_data.get("type"),
                source_provider=self.PROVIDER_NAME
            )
            store.register(doc)
            
        # Top-level securities (sometimes exist independently)
        for idx, sec in enumerate(self.raw.get("securities", [])):
            if isinstance(sec, str):
                continue
            s_ext_id = sec.get("id", f"top_sec_{idx}")
            security = Security(
                id=self._cid("Security", s_ext_id),
                external_id=str(s_ext_id),
                company_id="", # Unknown
                label=sec.get("label"),
                issue_date=sec.get("issue_date"),
                issuable_type=sec.get("issuable_type"),
                stock_type=sec.get("stock_type"),
                status=sec.get("status"),
                quantity=sec.get("quantity"),
                cost=sec.get("cost"),
                value=sec.get("value"),
                currency=sec.get("currency"),
                has_vesting=sec.get("has_vesting", False),
                source_provider=self.PROVIDER_NAME
            )
            store.register(security)

        log.info(f"Populated CanonicalEntityStore from Carta data: {len(store.companies)} companies, {len(store.funds)} funds")
