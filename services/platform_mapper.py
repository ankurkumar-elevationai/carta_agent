import logging
from typing import Dict, List, Any
from .canonical_store import CanonicalEntityStore
from .platform_schema import (
    InvInvestment, InvAssetExtraInfo, InvAssetTeam, InvAssetValuation,
    InvCapCall, InvestmentLog, InvInvestmentTransaction, InvInvestmentFirm,
    InvInvestmentFocus, InvInvestmentSector, InvInvestmentCertificate,
    InvInvestmentDistributionHistory, InvLiquidityDistribution,
    InvInvestmentExpense, InvInvestmentInterest, InvInvestmentService,
    InvAssetUsageLog, ExtraInfoRecentDevelopment, ResearchGrowingTraction
)

log = logging.getLogger(__name__)

class PlatformSchemaMapper:
    """Transforms Canonical Entities into Platform Schema compliant objects."""
    
    def __init__(self, store: CanonicalEntityStore):
        self.store = store
        
    def map_inv_investment(self) -> List[InvInvestment]:
        results = []
        for company in self.store.list_companies():
            agg = self.store.get_company_aggregate(company.id)
            
            # Simple aggregation from holding
            holding = agg.holdings[0] if agg.holdings else None
            valuation = agg.valuations[0] if agg.valuations else None
            
            inv = InvInvestment(
                asset_id=company.id,
                asset_name=company.name,
                investment_amount=holding.cash_cost if holding else None,
                valuation=valuation.post_money if valuation else None,
                irr=holding.irr_percentage if holding else None,
                investment_date=holding.held_since if holding else None,
                ownership_percentage=holding.ownership_pct if holding else None,
                asset_category="Venture"
            )
            results.append(inv)
        return results

    def map_inv_asset_extra_info(self) -> List[InvAssetExtraInfo]:
        results = []
        for company in self.store.list_companies():
            info = InvAssetExtraInfo(
                investment_id=company.id,
                industry_overview=company.description,
                # The rest are ENRICHMENT_REQUIRED
            )
            results.append(info)
        return results

    def map_inv_asset_team(self) -> List[InvAssetTeam]:
        results = []
        for company in self.store.list_companies():
            agg = self.store.get_company_aggregate(company.id)
            for person in agg.people:
                name_parts = person.name.split(" ", 1)
                first = name_parts[0]
                last = name_parts[1] if len(name_parts) > 1 else ""
                
                team = InvAssetTeam(
                    investment_id=company.id,
                    first_name=first,
                    last_name=last,
                    email=person.email,
                    designation=person.title
                )
                results.append(team)
        return results

    def map_inv_asset_valuation(self) -> List[InvAssetValuation]:
        results = []
        for company in self.store.list_companies():
            agg = self.store.get_company_aggregate(company.id)
            for val in agg.valuations:
                if val.post_money and val.valuation_date:
                    try:
                        year = val.valuation_date.split("-")[0] if "-" in val.valuation_date else val.valuation_date
                        v = InvAssetValuation(
                            investment_id=company.id,
                            amount=val.post_money,
                            year=year
                        )
                        results.append(v)
                    except Exception as e:
                        log.debug(f"Skipping valuation mapping error: {e}")
        return results

    def map_inv_cap_call(self) -> List[InvCapCall]:
        results = []
        for company in self.store.list_companies():
            agg = self.store.get_company_aggregate(company.id)
            for tx in agg.transactions:
                if tx.debit and tx.date:
                    call = InvCapCall(
                        investment_id=company.id,
                        amount=tx.debit,
                        notes=tx.description,
                        date=tx.date,
                        fund_name=None # Would need holding backref
                    )
                    results.append(call)
        return results

    def map_investment_log(self) -> List[InvestmentLog]:
        results = []
        for company in self.store.list_companies():
            agg = self.store.get_company_aggregate(company.id)
            cumulative_amount = 0.0
            for tx in sorted(agg.transactions, key=lambda x: x.date or ""):
                if tx.debit and tx.date:
                    cumulative_amount += tx.debit
                    log_entry = InvestmentLog(
                        investment_id=company.id,
                        investment_amount=cumulative_amount,
                        investment_date=tx.date
                    )
                    results.append(log_entry)
        return results

    def map_inv_investment_transaction(self) -> List[InvInvestmentTransaction]:
        results = []
        for company in self.store.list_companies():
            agg = self.store.get_company_aggregate(company.id)
            for tx in agg.transactions:
                amount = tx.debit if tx.debit else tx.credit
                direction = "Outflow" if tx.debit else "Inflow" if tx.credit else "Unknown"
                
                if amount:
                    inv_tx = InvInvestmentTransaction(
                        investment_id=company.id,
                        amount=amount,
                        name=tx.description,
                        tr_date=tx.date,
                        tr_direction=direction
                    )
                    results.append(inv_tx)
        return results

    def map_inv_investment_firm(self) -> List[InvInvestmentFirm]:
        results = []
        org = self.store.get_organization()
        if org:
            funds = self.store.list_funds()
            firm = InvInvestmentFirm(
                investment_id=org.id,
                company_name=org.name,
                fund_count=len(funds)
            )
            results.append(firm)
        return results

    def map_inv_investment_focus(self) -> List[InvInvestmentFocus]:
        results = []
        for company in self.store.list_companies():
            agg = self.store.get_company_aggregate(company.id)
            holding = agg.holdings[0] if agg.holdings else None
            valuation = agg.valuations[0] if agg.valuations else None
            
            focus = InvInvestmentFocus(
                investment_id=company.id,
                name=company.name,
                cost=holding.cash_cost if holding else None,
                current_year_valuation=valuation.post_money if valuation else None,
                moic=holding.multiple if holding else None
            )
            results.append(focus)
        return results

    def map_inv_investment_sector(self) -> List[InvInvestmentSector]:
        results = []
        for company in self.store.list_companies():
            if company.industry:
                sector = InvInvestmentSector(
                    investment_id=company.id,
                    name=company.industry,
                    stage_name=None # Typically ENRICHMENT_REQUIRED
                )
                results.append(sector)
        return results

    def map_inv_investment_certificate(self) -> List[InvInvestmentCertificate]:
        results = []
        for company in self.store.list_companies():
            agg = self.store.get_company_aggregate(company.id)
            for sec in agg.securities:
                if sec.label:
                    cert = InvInvestmentCertificate(
                        investment_id=company.id,
                        cert_number=sec.label,
                        issue_date=sec.issue_date,
                        cert_status=sec.status
                    )
                    results.append(cert)
        return results

    def map_inv_investment_distribution_history(self) -> List[InvInvestmentDistributionHistory]:
        results = []
        for company in self.store.list_companies():
            agg = self.store.get_company_aggregate(company.id)
            for tx in agg.transactions:
                if tx.credit and tx.date:
                    dist = InvInvestmentDistributionHistory(
                        investment_id=company.id,
                        total_amount=tx.credit,
                        lp_name=None # Contextual
                    )
                    results.append(dist)
        return results

    def map_inv_liquidity_distribution(self) -> List[InvLiquidityDistribution]:
        results = []
        for company in self.store.list_companies():
            agg = self.store.get_company_aggregate(company.id)
            for tx in agg.transactions:
                if tx.credit and tx.date:
                    liq = InvLiquidityDistribution(
                        investment_id=company.id,
                        amount=tx.credit,
                        source=tx.description
                    )
                    results.append(liq)
        return results

    # Stubs for missing data
    def map_inv_investment_expense(self) -> List[InvInvestmentExpense]: return []
    def map_inv_investment_interest(self) -> List[InvInvestmentInterest]: return []
    def map_inv_investment_service(self) -> List[InvInvestmentService]: return []
    def map_inv_asset_usage_log(self) -> List[InvAssetUsageLog]: return []
    def map_extra_info_recent_development(self) -> List[ExtraInfoRecentDevelopment]: return []
    def map_research_growing_traction(self) -> List[ResearchGrowingTraction]: return []
