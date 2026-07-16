# Platform Data Coverage and Carta Mapping Report

This report outlines how raw data extracted from **Carta's API** maps to the **Investment Module Platform** UI and database schema, based on visual analysis of the platform screenshots (found in `/img/`) and the extracted Carta dataset (`output/business_data.json` and Excel analyses).

---

## Executive Summary

We performed a comprehensive data coverage analysis by comparing the **19-table Investment Module Schema** and the **11 platform UI screenshots** against the **extracted Carta raw JSON data**.

### Key Findings
- **High Core Financial Alignment**: Carta provides excellent coverage for core venture transactions (capital calls, distributions), asset valuations (409A, post-money), portfolio companies list, share classes, certificate ledgers, and investor directories.
- **12 of 19 Tables Covered**: The platform data model is successfully populated by Carta for 12 core tables (including `inv_investment`, `inv_asset_team`, `inv_asset_valuation`, `inv_cap_call`, and `inv_investment_certificate`).
- **7 Unpopulated Tables (By Design)**: Tables like `inv_investment_expense`, `inv_investment_service`, and qualitative research (`research_growing_traction`) remain empty (returning 0 records/stubs). This is because Carta is an equity/cap table management ledger, not an operational accounting tool, CRM, or research database.
- **Enrichment Opportunities Identified**: Certain visual elements on the platform UI (e.g., Fund Manager AUM/website, round Lead Investors, sub-sector industry allocations, and waterfall exit modeling) are not tracked by Carta and require external data enrichment (e.g., PitchBook, CRMs, or manual GP input).

---

## View 1: Venture SPV (Screenshots 1, 2, 3)

The Venture SPV view (e.g., *OpenAI SPV*) displays the SPV's size, vintage, manager details, current performance, transactions, documents, and exit modeling.

| Platform UI Data Point | Screenshot | Coverage Status | Carta JSON Path / Source | Mapping & Transformation Logic |
| :--- | :--- | :--- | :--- | :--- |
| **SPV Name** | 1, 2 | 🟢 Full | `data.overview.name` or `data.name` | **DIRECT_MAP**: Maps directly to the asset name. |
| **SPV Total Size** | 1, 2 | 🟢 Full | `data.totals.committed[].value` | **DIRECT_MAP**: Sum of all LP committed capital for the SPV. |
| **Your Commitment** | 1, 2 | 🟢 Full | `holdings_summary.cash_cost` | **DIRECT_MAP**: Cash cost of the holding representing the LP's commitment. |
| **Commitment %** | 1, 2 | 🟡 Partial | Computed: `Your Commitment / SPV Total Size` | **COMPUTED**: Derived by dividing user cost by total SPV size. |
| **Current SPV Value** | 1, 2 | 🟢 Full | `totals.value` / `valuation.post_money` | **DIRECT_MAP**: Current gross asset value of the SPV. |
| **Your Position Value** | 1, 2 | 🟢 Full | `holdings_summary.value` | **DIRECT_MAP**: Market value of the user's specific position in the SPV. |
| **SPV MOIC** | 1, 2 | 🟢 Full | `holdings_summary.multiple` | **DIRECT_MAP**: Multiple on Invested Capital (TVPI) directly from holdings. |
| **Performance Chart** | 1 | 🟢 Full | `fmv_409a[].valuation` (historical) | **AGGREGATED**: Historical data points plotted chronologically by quarter. |
| **Transaction History** | 1 | 🟢 Full | `irr.transactions[]` | **DIRECT_MAP**: Maps list of transactions. Outflows are `debit`; inflows are `credit`. |
| **Strategy & Geography** | 1, 2 | 🔴 None | *No native source* | **ENRICHMENT_REQUIRED**: Hardcoded to `"Late Stage"` / `"North America"` stubs. |
| **Sector** | 1, 2 | 🟡 Partial | `profile.industry` | **DIRECT_MAP**: Industry category from profile; fallback to stub when blank. |
| **Vintage** | 1, 2 | 🟡 Partial | Derived from `holdings_summary.held_since` | **COMPUTED**: Year component extracted from the initial holding date. |
| **LPs Count** | 2 | 🟢 Full | Count of `investors` or `cap_table.rows[]` | **AGGREGATED**: Counts the unique LPs associated with the SPV entity. |
| **Entity Type** | 2 | 🔴 None | *No native source* | **ENRICHMENT_REQUIRED**: Hardcoded to `"Delaware LLC"` stub. |
| **Management Fee %** | 2 | 🟡 Partial | `fund_terms.management_fee` | **DIRECT_MAP**: Mapped from GP entity settings or setup terms. |
| **Carried Interest %** | 2 | 🟢 Full | `carried-interest.carried_interest_pct` | **DIRECT_MAP**: Mapped from carry share classes/terms. |
| **Waterfall Exit Model** | 2 | 🔴 None | *No native source* | **N/A (Platform Computed)**: Interactive scenario calculator computed on the platform side. |
| **TVPI / DPI / RVPI** | 2 | 🟡 Partial | Derived from transactions & holdings | **COMPUTED**: TVPI = `multiple`, DPI = `distributions / cost`, RVPI = `TVPI - DPI`. |
| **Net IRR %** | 2 | 🟢 Full | `holdings_summary.irr_percentage` | **DIRECT_MAP**: Internal rate of return extracted directly from holdings summary. |
| **Maturity / Reserves** | 2 | 🔴 None | *No native source* | **ENRICHMENT_REQUIRED**: Populated with null stubs; requires manual entry. |
| **Key People** | 2 | 🟢 Full | `contacts[].name` and `contacts[].title` | **DECOMPOSED**: Split into `first_name`, `last_name`, and mapped to designation. |
| **Mgmt Fees Paid** | 3 | 🔴 None | *No native source* | **ENRICHMENT_REQUIRED**: Mapped as a null stub (Table: `inv_investment_expense`). |
| **Distributions** | 3 | 🟢 Full | Sum of `irr.transactions[].credit` | **AGGREGATED**: Cumulative sum of transaction credits (distributions). |
| **Legal/Tax Documents** | 3 | 🟢 Full | `documents[].name`, `documents[].url` | **DIRECT_MAP**: List of legal, statements, report, and tax files. |
| **Needs Attention Alerts** | 3 | 🔴 None | *No native source* | **N/A (Platform Logic)**: Generated dynamically by platform-side compliance rules. |

---

## View 2: Venture Fund (Screenshots 4, 5, 6, 7, 8)

The Venture Fund view (e.g., *Sequoia Capital Fund XIV*) focuses on commitments, capital called, NAV, portfolio companies tables, capital call ledgers, and fund manager metadata.

| Platform UI Data Point | Screenshot | Coverage Status | Carta JSON Path / Source | Mapping & Transformation Logic |
| :--- | :--- | :--- | :--- | :--- |
| **Fund Name** | 4, 8 | 🟢 Full | `fund.name` or `data.fund.name` | **DIRECT_MAP**: Mapped directly to the fund's legal entity name. |
| **Committed Capital** | 4, 8 | 🟢 Full | `totals.committed` or `holdings.cash_cost` | **DIRECT_MAP**: Mapped to user's total capital commitment to the fund. |
| **Capital Called** | 4, 8 | 🟢 Full | `totals.contributed` | **DIRECT_MAP**: Total amount of capital called to date. |
| **Current NAV** | 4 | 🟢 Full | `totals.value` or `holdings_summary.value` | **DIRECT_MAP**: Current Net Asset Value of the user's interest. |
| **Distributions** | 4, 7 | 🟢 Full | `totals.distributed` | **DIRECT_MAP**: Total capital distributed back to LPs. |
| **Net IRR** | 4 | 🟢 Full | `holdings_summary.irr_percentage` | **DIRECT_MAP**: Net IRR percentage calculated for the fund. |
| **NAV Performance Chart** | 4 | 🟢 Full | `fmv_409a` or valuations history | **AGGREGATED**: Chronological list of historical quarterly NAV. |
| **Portfolio Companies** | 5 | 🟢 Full | `holdings` list under the Fund | **DIRECT_MAP**: Table of investments (`inv_investment_focus` / `inv_investment`). |
| **Portco Cost & GAV** | 5 | 🟢 Full | `holdings_summary.cash_cost` & `.value` | **DIRECT_MAP**: Individual portfolio company cost basis and current valuation. |
| **Portco Change (MOIC)** | 5 | 🟢 Full | `holdings_summary.multiple` | **DIRECT_MAP**: Maps company multiple to MOIC column. |
| **Portfolio Allocation** | 5, 6, 7 | 🔴 None | *No native source* | **ENRICHMENT_REQUIRED**: Sub-sector/allocation percentages require manual entry or CRM. |
| **Fund Manager Name** | 5, 6, 7, 8 | 🟢 Full | `firm.organization_name` | **DIRECT_MAP**: Mapped from the GP firm profile. |
| **Manager AUM / HQ / URL** | 5, 6, 7, 8 | 🔴 None | *No native source* | **ENRICHMENT_REQUIRED**: AUM, Headquarters, and Website are enriched from PitchBook. |
| **Capital Call History** | 6 | 🟢 Full | `active_capital_calls` / transactions | **DIRECT_MAP**: Capital call details (date, amount, status) mapped to `inv_cap_call`. |
| **Liquidity Ledger** | 7 | 🟢 Full | `irr.transactions[].credit` | **DIRECT_MAP**: Distribution details (date, amount, type) to `inv_liquidity_distribution`. |
| **Fund Manager Team** | 7, 8 | 🟢 Full | `contacts` (context: Fund GP) | **DECOMPOSED**: Mapped to team first name, last name, and designation. |
| **Fund Size** | 8 | 🟢 Full | `fund-accounting.fund_size` | **DIRECT_MAP**: Total capitalization of the fund. |
| **Investment Period** | 8 | 🔴 None | *No native source* | **ENRICHMENT_REQUIRED**: LP Agreement parameters are stubs; enriched manually. |

---

## View 3: Venture Direct (Screenshots 9, 10, 11)

The Venture Direct view (e.g., *Anduril Direct*) reflects direct equity holdings in startups, displaying share class categories, lead investors, valuations, cap tables, and key people.

| Platform UI Data Point | Screenshot | Coverage Status | Carta JSON Path / Source | Mapping & Transformation Logic |
| :--- | :--- | :--- | :--- | :--- |
| **Asset Name** | 9, 10, 11 | 🟢 Full | `company` or `PortfolioCompany.company` | **DIRECT_MAP**: Direct equity holding company name. |
| **Invested Amount** | 9 | 🟢 Full | `holdings_summary.cash_cost` | **DIRECT_MAP**: Maps user's total direct investment cost. |
| **Current Value** | 9, 10 | 🟢 Full | `holdings_summary.value` | **DIRECT_MAP**: Maps user's current share value based on latest FMV. |
| **Unrealized Gain** | 9 | 🟡 Partial | Computed: `Current Value - Invested` | **COMPUTED**: Derived by subtracting cost basis from current market value. |
| **Round / Stage** | 9, 10 | 🟢 Full | `share_classes[].name` or profile | **DIRECT_MAP**: Mapped from Series Round identifier (e.g., Series F). |
| **Lead Investor** | 9 | 🔴 None | *No native source* | **ENRICHMENT_REQUIRED**: Mapped as a null stub; require CRM/PitchBook enrichment. |
| **Cap Table (Shareholders)** | 10 | 🟢 Full | `cap_table.rows[]` / `securities` | **DIRECT_MAP**: Maps major classes (Preferred, Common, Options). |
| **Ownership %** | 10 | 🟢 Full | `cap_table.rows[].ownership` | **DIRECT_MAP**: Outstanding shares ownership percentage. |
| **Fully Diluted %** | 10 | 🟢 Full | `securities[].fully_diluted` | **DIRECT_MAP**: Mapped from fully diluted share ledger calculations. |
| **Last Valuation** | 10 | 🟢 Full | `valuation.post_money` | **DIRECT_MAP**: Mapped to last round valuation / post-money capitalization. |
| **Company Info / Profile** | 10 | 🟢 Full | `profile.description` / `.industry` | **DIRECT_MAP**: Mapped to asset overview and sector. |
| **Key People (Startups)** | 11 | 🟢 Full | `contacts[]` (context: Company) | **DECOMPOSED**: Startup founders, CEO, and board members names/titles mapped. |
| **Documents** | 11 | 🟢 Full | `closing_documents[]` / `documents` | **DIRECT_MAP**: Shareholder agreements, board updates, and report PDFs. |

---

## 19-Table Investment Schema Coverage Mapping

Below is a technical mapping of how the platform database tables align with Carta extraction data points.

| Table Name | Schema Type | Coverage | Primary Carta Source Field / JSON Endpoint | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **`inv_investment`** | Main Entity | **100%** | `PortfolioCompany`, `Holdings` | Core transaction details (asset_name, valuation, cost). |
| **`inv_asset_extra_info`** | Detail | **60%** | `profile.description` | Covers `industry_overview`. `thesis`/`financials` are stubs. |
| **`inv_asset_team`** | Contact | **100%** | `contacts[]` (name, email, title) | Decomposed (split name) to first/last name. |
| **`inv_asset_valuation`** | Metric | **100%** | `fmv_409a` or `valuations` list | Historical valuations list mapped chronologically. |
| **`inv_cap_call`** | Ledger | **100%** | `irr.transactions[].debit` | Outflow records representing capital calls. |
| **`investment_log`** | Ledger | **100%** | Cumulative sum of `debit` | Tracking cumulative cash invested over time. |
| **`inv_investment_transaction`**| Ledger | **100%** | `irr.transactions[]` | All inflow/outflow transaction ledgers. |
| **`inv_investment_firm`** | Parent Entity| **80%** | `firm.organization_name` / `firm_uuid` | Counts associated `funds[]`. AUM is a stub. |
| **`inv_investment_focus`** | Performance | **100%** | `holdings_summary` (cost, valuation, multiple) | Asset-level performance summary. |
| **`inv_investment_sector`** | Taxonomy | **50%** | `profile.industry` | High-level industry is mapped; stage name is a stub. |
| **`inv_investment_certificate`**| Ledger | **100%** | `cap_table.rows[]` (label, date, status) | Securities ledger certificates (e.g. CS-1, PS-A). |
| **`inv_investment_distribution_history`** | Ledger | **100%** | `irr.transactions[].credit` | Tracks distribution receipts by LP. |
| **`inv_liquidity_distribution`** | Ledger | **100%** | `irr.transactions[].credit` (credits) | Individual distributions mapped with descriptions. |
| **`inv_investment_expense`** | Operational | **0%** (Stub) | *No Carta Source* | Non-equity operational fees (Requires accounting integration). |
| **`inv_investment_interest`** | Yield | **0%** (Stub) | *No Carta Source* | Yields (Requires debt-ledger integration). |
| **`inv_investment_service`** | Operational | **0%** (Stub) | *No Carta Source* | Legal/GP fees (Requires accounting integration). |
| **`inv_asset_usage_log`** | Physical | **0%** (Stub) | *No Carta Source* | Fleet/jet usage logs (N/A for Venture/Equity). |
| **`extra_info_recent_development`**| Research | **0%** (Stub) | *No Carta Source* | PR / News events (Requires PitchBook/Google News). |
| **`research_growing_traction`** | Research | **0%** (Stub) | *No Carta Source* | Qualitative traction metrics (Requires CRM/custom data). |

---

## Gap Analysis & Enrichment Strategies

For the fields and tables where Carta coverage is `🔴 None` or `🟡 Partial`, we recommend the following enrichment paths to complete the Platform experience:

### 1. Venture Fund Managers (AUM, HQ, Website)
- **Gap**: Carta lists the name of the GP Firm but does not contain company descriptions, AUM values, headquarters locations, or website URLs.
- **Enrichment Path**: Integrate a secondary adapter connecting to the **PitchBook API** or the **SEC IAPD (Investment Adviser Public Disclosure) API** using the firm's legal name or CRD number.

### 2. Startup Lead Investors
- **Gap**: Carta tracks ownership percentages but doesn't flag which venture firm led a specific funding round.
- **Enrichment Path**: Query the **Crunchbase API** or the **PitchBook API matching the startup name and series (e.g. "Anduril Industries" + "Series F") to extract the lead investor name.

### 3. Investment Strategy & Geography
- **Gap**: Carta does not consistently enforce tagging portfolio companies by geography (e.g., North America) or investment stage strategy (e.g., Late Stage, Seed).
- **Enrichment Path**: Run an LLM scraping agent over the **PDF Pitch Decks or Investment Committee (IC) Memos** uploaded to the Carta documents tab to extract the company's geographical presence and core investment thesis.

### 4. Portfolio Allocation (Sub-Sectors)
- **Gap**: Carta contains broad industry categories but lacks granular, sub-sector percentage breakdowns (e.g., Aerospace 58%, Launch Systems 21%).
- **Enrichment Path**: Maintain a taxonomy mapping table in the platform where the portfolio team maps high-level Crunchbase categories to custom LP reporting buckets.

### 5. Distribution Waterfalls
- **Gap**: Waterfall modeling scenarios (e.g., exit proceeds allocation across LP shares and GP carry splits) are not calculated by standard cap table exports.
- **Enrichment Path**: Calculate waterfalls dynamically on the platform side by using the cap table share ledger (Table: `inv_investment_certificate`) combined with liquidation preferences and carry terms (Table: `inv_investment_firm`).
