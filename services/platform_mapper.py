import logging
from typing import Dict, List, Any
from .canonical_store import CanonicalEntityStore
from .platform_schema import (
    InvInvestment, InvAssetExtraInfo, InvAssetTeam, InvAssetValuation,
    InvCapCall, InvestmentLog, InvInvestmentTransaction, InvInvestmentFirm,
    InvInvestmentFocus, InvInvestmentSector, InvInvestmentCertificate,
    InvInvestmentDistributionHistory, InvLiquidityDistribution,
    InvInvestmentExpense, InvInvestmentInterest, InvInvestmentService,
    InvAssetUsageLog, ExtraInfoRecentDevelopment, ResearchGrowingTraction,
    PartnerCapitalAccountSummary
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
            
            val_amount = None
            if holding and holding.net_asset_value is not None:
                val_amount = holding.net_asset_value
            elif valuation and valuation.post_money is not None:
                val_amount = valuation.post_money

            inv = InvInvestment(
                asset_id=company.id,
                asset_name=company.name,
                investment_amount=holding.cash_cost if holding else None,
                valuation=val_amount,
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
                if val.post_money:
                    val_date = val.valuation_date or "2025-12-31"
                    try:
                        year = val_date.split("-")[0] if "-" in val_date else val_date
                        v = InvAssetValuation(
                            investment_id=company.id,
                            amount=val.post_money,
                            year=year,
                            date=val_date
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

    def map_partner_capital_account_summary(self) -> List[PartnerCapitalAccountSummary]:
        import json
        import os
        import re
        from pathlib import Path
        
        results = []
        project_root = Path(__file__).parent.parent
        exports_dir = project_root / "output" / "exports"
        if not exports_dir.exists():
            return []
            
        run_dirs = sorted(
            [d for d in exports_dir.iterdir() if d.is_dir()],
            key=lambda d: d.stat().st_mtime,
            reverse=True
        )
        if not run_dirs:
            return []
            
        for run_dir in run_dirs:
            latest_extracted = run_dir / "extracted"
            if not latest_extracted.exists():
                continue
                
            for root, _, files in os.walk(latest_extracted):
                for file in files:
                    if not file.endswith(".json") or file.startswith("_"):
                        continue
                    file_path = Path(root) / file
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            raw_data = json.load(f)
                        
                        if not isinstance(raw_data, dict):
                            continue
                            
                        meta = raw_data.get("_meta", {})
                        source_url = meta.get("source_url", "")
                        
                        if "get-partner-capital-account-summary-v2-lp" in source_url:
                            data = raw_data.get("data", {})
                            if not data:
                                continue
                                
                            fund_uuid = ""
                            partner_id = ""
                            start_date = ""
                            end_date = ""
                            
                            fund_match = re.search(r"fund_uuid=([a-f0-9\-]{36})", source_url)
                            if fund_match:
                                fund_uuid = fund_match.group(1)
                            partner_match = re.search(r"partner_id=([^&]+)", source_url)
                            if partner_match:
                                partner_id = partner_match.group(1)
                            start_match = re.search(r"start_date=([^&]+)", source_url)
                            if start_match:
                                start_date = start_match.group(1)
                            end_match = re.search(r"end_date=([^&]+)", source_url)
                            if end_match:
                                end_date = end_match.group(1)
                            
                            beginning_balance = None
                            contributions = None
                            distributions = None
                            net_income = None
                            ending_balance = None
                            
                            summary = data.get("summary", {}) or data
                            if isinstance(summary, dict):
                                # Helper to extract total from dict
                                def get_total(obj):
                                    if isinstance(obj, dict):
                                        return obj.get("total") or obj.get("lp") or obj.get("amount")
                                    return obj
    
                                beginning_balance = get_total(summary.get("beginning_balance") or summary.get("beginning"))
                                ending_balance = get_total(summary.get("ending_balance") or summary.get("ending"))
                                
                                contributions = get_total(summary.get("total_contributions_period") or summary.get("contributions") or summary.get("contributed"))
                                distributions = get_total(summary.get("distributions") or summary.get("distributed"))
                                
                                net_income = get_total(summary.get("net_income") or summary.get("income"))
                                
                                # Derive net income if not explicitly provided
                                if net_income is None and beginning_balance is not None and ending_balance is not None:
                                    try:
                                        bb_val = float(beginning_balance or 0)
                                        eb_val = float(ending_balance or 0)
                                        cb_val = float(contributions or 0)
                                        db_val = float(distributions or 0)
                                        # Ending = Beginning + Contrib - Dist + Net Income => Net Income = Ending - Beginning - Contrib + Dist
                                        net_income = eb_val - bb_val - cb_val + abs(db_val)
                                    except:
                                        pass
                                
                            def format_amount(val):
                                if val is None:
                                    return None
                                try:
                                    return float(val)
                                except:
                                    return None
                                    
                            item = PartnerCapitalAccountSummary(
                                investment_id=meta.get("entity_name") or fund_uuid or "Unknown Fund",
                                partner_id=partner_id,
                                fund_uuid=fund_uuid,
                                start_date=start_date,
                                end_date=end_date,
                                beginning_balance=format_amount(beginning_balance),
                                contributions=format_amount(contributions),
                                distributions=format_amount(distributions),
                                net_income=format_amount(net_income),
                                ending_balance=format_amount(ending_balance),
                                currency=data.get("currency", "USD")
                            )
                            results.append(item)
                    except Exception as e:
                        log.error(f"Error parsing capital account summary file: {e}")
                    
        return results

