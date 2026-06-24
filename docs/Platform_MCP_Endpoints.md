# Platform Schema MCP Endpoints Specification

This document details the newly exposed Model Context Protocol (MCP) endpoints that adhere to the 19-table Investment Module platform schema. These endpoints provide a canonical, provider-agnostic interface for agentic workflows to interact with investment data.

## Resources

### 1. Platform Data Coverage
- **URI pattern:** `platform://{tenant_id}/coverage`
- **Description:** Exposes a real-time field population coverage matrix. Automatically calculates what percentage of the platform schema fields are populated by the underlying data provider (e.g., Carta).
- **MIME Type:** `application/json`

---

## Tools

All platform schema tools return a standardized JSON envelope to ensure backward compatibility and strict API contracts.

**Standard Response Envelope:**
```json
{
  "schema_version": "v1",
  "mapper_version": "v1",
  "table": "<table_name>",
  "record_count": 0,
  "data": [ ... ]
}
```

### 1. get_investments
- **Target Table:** `inv_investment`
- **Description:** Returns all investments, mapping the `PortfolioCompany` and `Holding` canonical entities into the core platform asset registry. Contains valuation, IRR, cash cost, and ownership percentage.

### 2. get_investment_extra_info
- **Target Table:** `inv_asset_extra_info`
- **Description:** Returns qualitative research information. *Note: Investment thesis and tailwinds are pending Phase 2 enrichment.*

### 3. get_investment_team
- **Target Table:** `inv_asset_team`
- **Description:** Returns key people, founders, and contacts associated with the investment.

### 4. get_investment_valuations
- **Target Table:** `inv_asset_valuation`
- **Description:** Returns historical valuations (e.g., 409A and Post-Money).

### 5. get_capital_calls
- **Target Table:** `inv_cap_call`
- **Description:** Returns debit transactions classified as capital calls against an investment.

### 6. get_investment_log
- **Target Table:** `investment_log`
- **Description:** Returns point-in-time value snapshots tracking cumulative investment amounts over time.

### 7. get_investment_transactions
- **Target Table:** `inv_investment_transaction`
- **Description:** Returns all inflow and outflow transactions associated with an investment.

### 8. get_investment_firm
- **Target Table:** `inv_investment_firm`
- **Description:** Returns the GP/firm profile including AUM and the number of active funds.

### 9. get_investment_focus
- **Target Table:** `inv_investment_focus`
- **Description:** Returns the portfolio focus overview, including current year valuation and Multiple on Invested Capital (MOIC).

### 10. get_investment_sectors
- **Target Table:** `inv_investment_sector`
- **Description:** Returns the sector and stage classification of the investments.

### 11. get_investment_certificates
- **Target Table:** `inv_investment_certificate`
- **Description:** Returns share certificates, issue dates, and certificate status from the underlying cap tables.

### 12. get_distribution_history
- **Target Table:** `inv_investment_distribution_history`
- **Description:** Returns credit transactions classified as distribution events.

### 13. get_liquidity_distributions
- **Target Table:** `inv_liquidity_distribution`
- **Description:** Returns detailed liquidity event distributions and their sources.

### 14. get_investment_expenses
- **Target Table:** `inv_investment_expense`
- **Description:** Returns categorized expenses associated with the investment. *(Currently a stub pending enrichment)*.

### 15. get_investment_interest
- **Target Table:** `inv_investment_interest`
- **Description:** Returns interest earnings on the investment. *(Currently a stub pending enrichment)*.

### 16. get_investment_services
- **Target Table:** `inv_investment_service`
- **Description:** Returns service records and associated vendor costs. *(Currently a stub pending enrichment)*.

### 17. get_usage_logs
- **Target Table:** `inv_asset_usage_log`
- **Description:** Returns usage logs for physical assets. *(Returns empty for Venture investments)*.

### 18. get_recent_developments
- **Target Table:** `extra_info_recent_development`
- **Description:** Returns tracked news and recent developments. *(Currently a stub pending enrichment)*.

### 19. get_growth_signals
- **Target Table:** `research_growing_traction`
- **Description:** Returns extracted traction and growth signals. *(Currently a stub pending enrichment)*.
