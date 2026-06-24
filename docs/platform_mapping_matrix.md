# Platform Mapping Matrix (Carta → Canonical → Platform)

This document details how data flows from Carta's raw JSON extracts, through the Canonical Entity Store, into the 19-table Investment Module Schema.

## Data Transformation Strategy

There are 5 transform categories used in this integration:
- **DIRECT_MAP**: Field rename and type cast (e.g., `company` → `asset_name`)
- **COMPUTED**: Derived from formulas (e.g., `current_year_moic` = `valuation` / `cost`)
- **DECOMPOSED**: Single source → multiple targets (e.g., `contact.name` → `first_name` + `last_name`)
- **AGGREGATED**: Multiple sources → single target (e.g., transaction credits → `distribution_history`)
- **ENRICHMENT_REQUIRED**: No Carta source. Populated with null stubs.

*(Note: Physical asset fields like `vin`, `tail_id`, and `carat_weight` are marked **NA_FOR_VENTURE** and permanently nulled out.)*

---

## Table 1: `inv_investment`
| Target Field | Type | Canonical Entity | Carta Source | Status |
|---|---|---|---|---|
| `asset_id` | `uuid` | `PortfolioCompany` | `corporation_id` | DIRECT_MAP |
| `asset_name` | `string` | `PortfolioCompany` | `company` | DIRECT_MAP |
| `investment_amount` | `float` | `Holding` | `holdings_summary.cash_cost` | DIRECT_MAP |
| `valuation` | `float` | `Valuation` | `valuation.post_money` | DIRECT_MAP |
| `irr` | `float` | `Holding` | `holdings_summary.irr_percentage` | DIRECT_MAP |
| `investment_date` | `date` | `Holding` | `holdings_summary.held_since` | DIRECT_MAP |
| `ownership_percentage` | `float` | `Holding` | `holdings_summary.ownership_pct` | DIRECT_MAP |
| `asset_category` | `string` | — | Hardcoded to `"Venture"` | COMPUTED |

## Table 2: `inv_asset_extra_info`
| Target Field | Type | Canonical Entity | Carta Source | Status |
|---|---|---|---|---|
| `investment_id` | `uuid` | `PortfolioCompany` | `corporation_id` | DIRECT_MAP |
| `industry_overview` | `text` | `PortfolioCompany` | `profile.description` | DIRECT_MAP |
| `investment_thesis` | `text` | — | None | ENRICHMENT_REQUIRED |
| `industry_tailwinds` | `text` | — | None | ENRICHMENT_REQUIRED |
| `customer_segment` | `text` | — | None | ENRICHMENT_REQUIRED |
| `financials` | `text` | — | None | ENRICHMENT_REQUIRED |

## Table 3: `inv_asset_team`
| Target Field | Type | Canonical Entity | Carta Source | Status |
|---|---|---|---|---|
| `investment_id` | `uuid` | `PortfolioCompany` | `corporation_id` | DIRECT_MAP |
| `first_name` | `string` | `Person` | `contacts[].name` (split) | DECOMPOSED |
| `last_name` | `string` | `Person` | `contacts[].name` (split) | DECOMPOSED |
| `email` | `string` | `Person` | `contacts[].email` | DIRECT_MAP |
| `designation` | `string` | `Person` | `contacts[].title` | DIRECT_MAP |

## Table 4: `inv_asset_valuation`
| Target Field | Type | Canonical Entity | Carta Source | Status |
|---|---|---|---|---|
| `investment_id` | `uuid` | `PortfolioCompany` | `corporation_id` | DIRECT_MAP |
| `amount` | `float` | `Valuation` | `fmv_409a[].valuation` | DIRECT_MAP |
| `year` | `string` | `Valuation` | `fmv_409a[].date` (year extracted) | COMPUTED |

## Table 5: `inv_cap_call`
| Target Field | Type | Canonical Entity | Carta Source | Status |
|---|---|---|---|---|
| `investment_id` | `uuid` | `PortfolioCompany` | `corporation_id` | DIRECT_MAP |
| `amount` | `float` | `Transaction` | `irr.transactions[].debit` | DIRECT_MAP |
| `notes` | `text` | `Transaction` | `irr.transactions[].description` | DIRECT_MAP |
| `date` | `date` | `Transaction` | `irr.transactions[].date` | DIRECT_MAP |
| `fund_name` | `string` | `Fund` | Derived from context | COMPUTED |

## Table 6: `investment_log`
| Target Field | Type | Canonical Entity | Carta Source | Status |
|---|---|---|---|---|
| `investment_id` | `uuid` | `PortfolioCompany` | `corporation_id` | DIRECT_MAP |
| `investment_amount` | `float` | `Transaction` | Cumulative sum of `debit` | AGGREGATED |
| `investment_date` | `date` | `Transaction` | `irr.transactions[].date` | DIRECT_MAP |

## Table 7: `inv_investment_transaction`
| Target Field | Type | Canonical Entity | Carta Source | Status |
|---|---|---|---|---|
| `investment_id` | `uuid` | `PortfolioCompany` | `corporation_id` | DIRECT_MAP |
| `amount` | `float` | `Transaction` | `debit` or `credit` | COMPUTED |
| `name` | `string` | `Transaction` | `irr.transactions[].description` | DIRECT_MAP |
| `tr_date` | `date` | `Transaction` | `irr.transactions[].date` | DIRECT_MAP |
| `tr_direction` | `string` | `Transaction` | "Inflow" or "Outflow" | COMPUTED |

## Table 8: `inv_investment_firm`
| Target Field | Type | Canonical Entity | Carta Source | Status |
|---|---|---|---|---|
| `investment_id` | `uuid` | `Organization` | `firm.firm_uuid` | DIRECT_MAP |
| `company_name` | `string` | `Organization` | `firm.organization_name` | DIRECT_MAP |
| `fund_count` | `int` | `Fund` | Count of `funds[]` | AGGREGATED |

## Table 9: `inv_investment_focus`
| Target Field | Type | Canonical Entity | Carta Source | Status |
|---|---|---|---|---|
| `investment_id` | `uuid` | `PortfolioCompany` | `corporation_id` | DIRECT_MAP |
| `name` | `string` | `PortfolioCompany` | `company` | DIRECT_MAP |
| `cost` | `float` | `Holding` | `holdings_summary.cash_cost` | DIRECT_MAP |
| `current_year_valuation` | `float` | `Valuation` | `valuation.post_money` | DIRECT_MAP |
| `moic` | `float` | `Holding` | `holdings_summary.multiple` | DIRECT_MAP |

## Table 10: `inv_investment_sector`
| Target Field | Type | Canonical Entity | Carta Source | Status |
|---|---|---|---|---|
| `investment_id` | `uuid` | `PortfolioCompany` | `corporation_id` | DIRECT_MAP |
| `name` | `string` | `PortfolioCompany` | `profile.industry` | DIRECT_MAP |
| `stage_name` | `string` | — | None | ENRICHMENT_REQUIRED |

## Table 11: `inv_investment_certificate`
| Target Field | Type | Canonical Entity | Carta Source | Status |
|---|---|---|---|---|
| `investment_id` | `uuid` | `PortfolioCompany` | `corporation_id` | DIRECT_MAP |
| `cert_number` | `string` | `Security` | `cap_table.rows[].label` | DIRECT_MAP |
| `issue_date` | `date` | `Security` | `cap_table.rows[].issue_date`| DIRECT_MAP |
| `cert_status` | `string` | `Security` | `cap_table.rows[].status` | DIRECT_MAP |

## Table 12: `inv_investment_distribution_history`
| Target Field | Type | Canonical Entity | Carta Source | Status |
|---|---|---|---|---|
| `investment_id` | `uuid` | `PortfolioCompany` | `corporation_id` | DIRECT_MAP |
| `total_amount` | `float` | `Transaction` | `irr.transactions[].credit` | DIRECT_MAP |

## Table 13: `inv_liquidity_distribution`
| Target Field | Type | Canonical Entity | Carta Source | Status |
|---|---|---|---|---|
| `investment_id` | `uuid` | `PortfolioCompany` | `corporation_id` | DIRECT_MAP |
| `amount` | `float` | `Transaction` | `irr.transactions[].credit` | DIRECT_MAP |
| `source` | `string` | `Transaction` | `irr.transactions[].description`| DIRECT_MAP |

## Empty & Null Tables (Enrichment Required)
The following tables currently have 0% field coverage from Carta and act as placeholders for Phase 2 Enrichment:
- `inv_investment_expense`
- `inv_investment_interest`
- `inv_investment_service`
- `inv_asset_usage_log`
- `extra_info_recent_development`
- `research_growing_traction`
