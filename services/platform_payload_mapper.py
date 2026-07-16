from typing import List, Dict, Optional
from .platform_schema import InvAssetValuation
from .platform_payloads import PortfolioInvestmentUpdatePayload, PortfolioInvestmentUpdateData

class PlatformPayloadMapper:
    """Transforms Platform Table Models into final API Payloads."""

    def map_portfolio_investment_update(self, valuations: List[InvAssetValuation]) -> List[PortfolioInvestmentUpdatePayload]:
        # Group by investment_id
        grouped: Dict[str, List[InvAssetValuation]] = {}
        for val in valuations:
            if val.investment_id not in grouped:
                grouped[val.investment_id] = []
            grouped[val.investment_id].append(val)

        payloads = []
        for investment_id, vals in grouped.items():
            # Sort by full date descending. Fallback to year or empty string if None.
            # This ensures we get the absolutely latest valuation based on full date.
            sorted_vals = sorted(
                vals, 
                key=lambda x: x.date if x.date else x.year, 
                reverse=True
            )
            latest = sorted_vals[0] if sorted_vals else None

            data = PortfolioInvestmentUpdateData(
                valuation=latest.amount if latest else None,
                valuation_year=latest.year if latest else None
            )

            payload = PortfolioInvestmentUpdatePayload(
                org_id="__ORG_ID__",
                user_id="__USER_ID__",
                investment_id=investment_id,
                data=data
            )
            payloads.append(payload)

        return payloads
